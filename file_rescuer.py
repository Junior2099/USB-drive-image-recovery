#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
File Rescuer - Programa para recuperar arquivos de imagem (JPEG e PNG)
de dispositivos de armazenamento usando Magic Bytes.
"""

import os
import sys
import uuid
import platform
from datetime import datetime
from pathlib import Path
from typing import Tuple, Optional, List
from PIL import Image
from io import BytesIO


# Definições dos Magic Bytes
JPEG_HEADER = bytes([0xFF, 0xD8])
JPEG_FOOTER = bytes([0xFF, 0xD9])

PNG_HEADER = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])
PNG_FOOTER = bytes([0x49, 0x45, 0x4E, 0x44, 0xAE, 0x42, 0x60, 0x82])  # IEND chunk

# Tamanho do bloco para leitura (32 MB)
BLOCK_SIZE = 32 * 1024 * 1024  # 32 MB


def get_raw_device_path(device_path: str) -> str:
    """
    Converte o caminho do dispositivo para formato raw necessário para acesso direto.
    
    Args:
        device_path: Caminho original do dispositivo
        
    Returns:
        Caminho no formato raw apropriado para o sistema operacional
    """
    if platform.system() == 'Windows':
        # Remove barras finais e normaliza
        path = device_path.rstrip('\\/').upper()
        
        # Se já está no formato \\.\E:, retorna como está
        if path.startswith('\\\\.\\'):
            return path
        
        # Se é uma letra de unidade (E:, F:, etc.)
        if len(path) == 2 and path[1] == ':':
            return f'\\\\.\\{path}'
        
        # Se é um caminho completo como E:\ ou E:\folder
        if ':' in path:
            drive_letter = path[0] + ':'
            return f'\\\\.\\{drive_letter}'
        
        # Se não conseguiu determinar, tenta adicionar \\.\
        return f'\\\\.\\{device_path}'
    else:
        # Linux/Unix - retorna como está (já deve ser /dev/sdb1, etc.)
        return device_path


def get_device_size(device_path: str) -> Optional[int]:
    """
    Obtém o tamanho do dispositivo em bytes.
    
    Args:
        device_path: Caminho do dispositivo
        
    Returns:
        Tamanho em bytes ou None se não conseguir determinar
    """
    try:
        if platform.system() == 'Windows':
            import ctypes
            from ctypes import wintypes
            
            # Tenta obter o tamanho usando DeviceIoControl
            GENERIC_READ = 0x80000000
            OPEN_EXISTING = 3
            FILE_ATTRIBUTE_NORMAL = 0x80
            
            handle = ctypes.windll.kernel32.CreateFileW(
                device_path,
                GENERIC_READ,
                0,
                None,
                OPEN_EXISTING,
                FILE_ATTRIBUTE_NORMAL,
                None
            )
            
            if handle == -1:
                return None
            
            try:
                # IOCTL_DISK_GET_LENGTH_INFO
                IOCTL_DISK_GET_LENGTH_INFO = 0x74005C
                length_info = ctypes.create_string_buffer(8)
                bytes_returned = wintypes.DWORD()
                
                result = ctypes.windll.kernel32.DeviceIoControl(
                    handle,
                    IOCTL_DISK_GET_LENGTH_INFO,
                    None,
                    0,
                    length_info,
                    8,
                    ctypes.byref(bytes_returned),
                    None
                )
                
                if result:
                    size = int.from_bytes(length_info.raw[:8], byteorder='little', signed=False)
                    return size
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
        else:
            # Linux - tenta usar ioctl BLKGETSIZE64
            try:
                import fcntl
                import struct
                
                with open(device_path, 'rb') as f:
                    # BLKGETSIZE64 = 0x80081272
                    BLKGETSIZE64 = 0x80081272
                    size = struct.pack('L', 0)  # 8 bytes para 64-bit
                    try:
                        fcntl.ioctl(f.fileno(), BLKGETSIZE64, size)
                        return struct.unpack('Q', size)[0]  # Q = unsigned long long (64-bit)
                    except (IOError, OSError):
                        # Se ioctl falhar, tenta usar stat
                        import stat
                        st = os.stat(device_path)
                        if stat.S_ISBLK(st.st_mode):
                            # Para dispositivos de bloco, pode não conseguir o tamanho exato
                            # Retorna None para indicar que não conseguiu determinar
                            pass
            except Exception:
                pass
    except Exception:
        pass
    
    return None


def find_magic_bytes(data: bytes, magic_bytes: bytes, start_pos: int = 0) -> Optional[int]:
    """
    Encontra a posição dos Magic Bytes no buffer de dados.
    
    Args:
        data: Buffer de bytes para procurar
        magic_bytes: Sequência de bytes a procurar
        start_pos: Posição inicial para começar a busca
        
    Returns:
        Posição do início dos Magic Bytes ou None se não encontrado
    """
    pos = data.find(magic_bytes, start_pos)
    return pos if pos != -1 else None


def validate_image(data: bytes, format: str) -> bool:
    """
    Valida se uma imagem está corrompida ou não.
    
    Args:
        data: Bytes da imagem
        format: Formato da imagem ('jpeg' ou 'png')
        
    Returns:
        True se a imagem é válida, False se está corrompida
    """
    if not data:
        return False
    
    try:
        if format.lower() == 'jpeg':
            # Verifica se termina com FF D9
            if not data.endswith(JPEG_FOOTER):
                return False
            
            # Tenta decodificar com Pillow
            img = Image.open(BytesIO(data))
            img.verify()  # Verifica a integridade
            return True
            
        elif format.lower() == 'png':
            # Verifica se contém o IEND chunk no final
            if PNG_FOOTER not in data[-100:]:  # Verifica nos últimos 100 bytes
                return False
            
            # Tenta decodificar com Pillow
            img = Image.open(BytesIO(data))
            img.verify()  # Verifica a integridade
            return True
            
    except Exception:
        # Se houver qualquer erro na decodificação, a imagem está corrompida
        return False
    
    return False


def analyze_data_distribution(found_files_count: int, total_blocks: int) -> str:
    """
    Analisa a distribuição de dados no dispositivo.
    
    Args:
        found_files_count: Número total de arquivos encontrados
        total_blocks: Número total de blocos varridos
        
    Returns:
        String descrevendo o estado de populamento do disco
    """
    if total_blocks == 0:
        return "Dispositivo vazio ou não acessível."
    
    # Calcula arquivos por MB (assumindo blocos de 32 MB)
    files_per_mb = found_files_count / (total_blocks * 32) if total_blocks > 0 else 0
    
    if found_files_count == 0:
        return "Vazio ou recém-formatado."
    elif files_per_mb < 0.1:  # Menos de 0.1 arquivo por MB
        return "Parcialmente populado."
    elif files_per_mb < 1.0:  # Entre 0.1 e 1 arquivo por MB
        return "Bem populado."
    else:  # Mais de 1 arquivo por MB
        return "Muito populado."


def save_file(data: bytes, format: str, output_directory: str, log_callback=None) -> str:
    """
    Salva um arquivo de imagem no diretório de saída.
    
    Args:
        data: Bytes da imagem
        format: Formato da imagem ('jpeg' ou 'png')
        output_directory: Diretório onde salvar o arquivo
        log_callback: Função opcional para logging
        
    Returns:
        Nome do arquivo salvo
    """
    # Cria o diretório se não existir
    Path(output_directory).mkdir(parents=True, exist_ok=True)
    
    # Gera nome único usando timestamp e UUID
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = str(uuid.uuid4())[:8]
    extension = '.jpg' if format.lower() == 'jpeg' else '.png'
    filename = f"rescued_{timestamp}_{unique_id}{extension}"
    
    filepath = os.path.join(output_directory, filename)
    
    # Salva o arquivo
    with open(filepath, 'wb') as f:
        f.write(data)
    
    message = f"Arquivo salvo: {filename}"
    if log_callback:
        log_callback(message)
    else:
        print(message)
    
    return filename


def scan_device(device_path: str, output_directory: str = "rescued_files", progress_callback=None, log_callback=None) -> Tuple[int, int]:
    """
    Função principal que varre o dispositivo em busca de arquivos de imagem.
    
    Args:
        device_path: Caminho do dispositivo (ex: /dev/sdb1, E:\, etc.)
        output_directory: Diretório onde salvar os arquivos recuperados
        progress_callback: Função opcional chamada com (found_files, total_blocks) para atualizar progresso
        log_callback: Função opcional chamada com mensagens de log
        
    Returns:
        Tupla com (número de arquivos encontrados, número de blocos varridos)
    """
    found_files = 0
    total_blocks = 0
    buffer_overflow = b''  # Buffer para dados que podem estar entre blocos
    pending_file = None  # Armazena arquivo iniciado mas não finalizado
    
    def log(message):
        if log_callback:
            log_callback(message)
        else:
            print(message)
    
    log(f"Iniciando varredura do dispositivo: {device_path}")
    log(f"Diretório de saída: {output_directory}")
    log("-" * 60)
    
    # Converte para caminho raw se necessário
    raw_device_path = get_raw_device_path(device_path)
    
    if raw_device_path != device_path:
        log(f"Convertendo caminho para formato raw: {device_path} -> {raw_device_path}")
    
    # Verifica se o caminho parece ser um diretório normal (não raw)
    if platform.system() == 'Windows':
        if not raw_device_path.startswith('\\\\.\\') and os.path.isdir(device_path):
            log("AVISO: Você está acessando um diretório, não o dispositivo raw!")
            log("Para recuperar arquivos APAGADOS, use o formato: \\\\.\\E:")
            log("Onde E: é a letra da sua unidade.")
            log("Continuando com acesso ao diretório (apenas arquivos existentes)...")
    
    # Tenta obter o tamanho do dispositivo
    device_size = get_device_size(raw_device_path)
    if device_size:
        size_mb = device_size / (1024 * 1024)
        size_gb = device_size / (1024 * 1024 * 1024)
        if size_gb >= 1:
            log(f"Tamanho do dispositivo: {size_gb:.2f} GB ({device_size:,} bytes)")
        else:
            log(f"Tamanho do dispositivo: {size_mb:.2f} MB ({device_size:,} bytes)")
    
    try:
        # No Windows, precisamos abrir com modo binário e sem buffering para acesso raw
        if platform.system() == 'Windows':
            # Tenta abrir o dispositivo raw
            try:
                device = open(raw_device_path, 'rb')
            except (PermissionError, OSError):
                # Se falhar, tenta o caminho original
                log("Aviso: Não foi possível acessar como dispositivo raw. Tentando caminho normal...")
                log("Nota: Para recuperar arquivos apagados, execute como Administrador e use o formato \\\\.\\E:")
                device = open(device_path, 'rb')
        else:
            device = open(raw_device_path, 'rb')
        
        try:
            bytes_read_total = 0
            
            while True:
                # Lê um bloco de 32 MB
                block = device.read(BLOCK_SIZE)
                
                if not block:
                    # Processa arquivo pendente antes de sair
                    if pending_file:
                        file_data, found_format = pending_file
                        if validate_image(file_data, found_format):
                            filename = save_file(file_data, found_format, output_directory, log_callback)
                            found_files += 1
                            if progress_callback:
                                progress_callback(found_files, total_blocks)
                    break
                
                empty_blocks_count = 0  # Reset contador se leu dados
                bytes_read_total += len(block)
                
                total_blocks += 1
                if log_callback is None:
                    print(f"Varrendo bloco {total_blocks}...", end='\r')
                
                # Atualiza progresso via callback
                if progress_callback:
                    progress_callback(found_files, total_blocks)
                
                # Combina o buffer de overflow com o novo bloco
                search_data = buffer_overflow + block
                buffer_overflow = b''
                
                # Se há um arquivo pendente, continua procurando pelo footer
                if pending_file:
                    file_data, found_format = pending_file
                    footer = JPEG_FOOTER if found_format == 'jpeg' else PNG_FOOTER
                    footer_pos = find_magic_bytes(search_data, footer, 0)
                    
                    if footer_pos is not None:
                        # Footer encontrado, completa o arquivo
                        file_end = footer_pos + len(footer)
                        complete_file_data = file_data + search_data[:file_end]
                        
                        if validate_image(complete_file_data, found_format):
                            filename = save_file(complete_file_data, found_format, output_directory, log_callback)
                            found_files += 1
                            if progress_callback:
                                progress_callback(found_files, total_blocks)
                        
                        # Remove os dados já processados
                        search_data = search_data[file_end:]
                        pending_file = None
                    else:
                        # Footer ainda não encontrado, adiciona mais dados
                        pending_file = (file_data + search_data, found_format)
                        # Mantém apenas os últimos bytes para próxima busca
                        max_header_len = max(len(JPEG_HEADER), len(PNG_HEADER))
                        buffer_overflow = search_data[-max_header_len:] if len(search_data) > max_header_len else search_data
                        continue
                
                current_pos = 0
                
                while current_pos < len(search_data):
                    # Procura por JPEG
                    jpeg_start = find_magic_bytes(search_data, JPEG_HEADER, current_pos)
                    
                    # Procura por PNG
                    png_start = find_magic_bytes(search_data, PNG_HEADER, current_pos)
                    
                    # Determina qual formato foi encontrado primeiro
                    found_format = None
                    file_start = None
                    
                    if jpeg_start is not None and png_start is not None:
                        if jpeg_start < png_start:
                            found_format = 'jpeg'
                            file_start = jpeg_start
                        else:
                            found_format = 'png'
                            file_start = png_start
                    elif jpeg_start is not None:
                        found_format = 'jpeg'
                        file_start = jpeg_start
                    elif png_start is not None:
                        found_format = 'png'
                        file_start = png_start
                    
                    if found_format is None:
                        break
                    
                    # Procura pelo footer correspondente
                    footer = JPEG_FOOTER if found_format == 'jpeg' else PNG_FOOTER
                    min_search_pos = file_start + (len(PNG_HEADER) if found_format == 'png' else len(JPEG_HEADER))
                    footer_pos = find_magic_bytes(search_data, footer, min_search_pos)
                    
                    if footer_pos is not None:
                        # Arquivo completo encontrado
                        file_end = footer_pos + len(footer)
                        file_data = search_data[file_start:file_end]
                        
                        # Valida a imagem
                        if validate_image(file_data, found_format):
                            filename = save_file(file_data, found_format, output_directory, log_callback)
                            found_files += 1
                            if progress_callback:
                                progress_callback(found_files, total_blocks)
                        
                        current_pos = file_end
                    else:
                        # Footer não encontrado neste bloco - arquivo pode continuar no próximo
                        file_data = search_data[file_start:]
                        pending_file = (file_data, found_format)
                        # Mantém os últimos bytes que podem conter início de outro arquivo
                        max_header_len = max(len(JPEG_HEADER), len(PNG_HEADER))
                        if len(search_data) > max_header_len:
                            buffer_overflow = search_data[-max_header_len:]
                        break
                
                # Se não há arquivo pendente, mantém os últimos bytes para próxima busca
                if not pending_file and len(search_data) > 0:
                    max_header_len = max(len(JPEG_HEADER), len(PNG_HEADER))
                    if len(search_data) > max_header_len:
                        buffer_overflow = search_data[-max_header_len:]
        
        finally:
            device.close()
    
    except PermissionError:
        error_msg = (
            f"\nErro: Permissão negada para acessar {device_path}\n"
            f"Para recuperar arquivos apagados, você precisa:\n"
        )
        if platform.system() == 'Windows':
            error_msg += (
                "1. Executar como Administrador\n"
                f"2. Usar o formato: \\\\.\\E: (onde E: é sua unidade)\n"
                f"   Exemplo: python file_rescuer.py \\\\.\\E:\n"
            )
        else:
            error_msg += (
                "1. Executar com sudo\n"
                "2. Usar o caminho do dispositivo raw (ex: /dev/sdb1)\n"
                "   Exemplo: sudo python file_rescuer.py /dev/sdb1\n"
            )
        log(error_msg)
        return found_files, total_blocks
    except FileNotFoundError:
        error_msg = f"\nErro: Dispositivo não encontrado: {device_path}\n"
        if platform.system() == 'Windows':
            error_msg += (
                "No Windows, para acessar dispositivo raw, use:\n"
                f"  - \\\\.\\E: (para unidade E:)\n"
                f"  - \\\\.\\PhysicalDrive0 (para disco físico 0)\n"
            )
        else:
            error_msg += (
                "No Linux, use o caminho do dispositivo raw:\n"
                "  - /dev/sdb1 (para partição)\n"
                "  - /dev/sdb (para disco inteiro)\n"
            )
        log(error_msg)
        return found_files, total_blocks
    except Exception as e:
        log(f"\nErro durante a varredura: {e}")
        import traceback
        log(f"Detalhes: {traceback.format_exc()}")
        return found_files, total_blocks
    
    log(f"\n{'=' * 60}")
    log(f"Varredura concluída!")
    log(f"Blocos varridos: {total_blocks}")
    log(f"Arquivos encontrados e salvos: {found_files}")
    log(f"Estado do dispositivo: {analyze_data_distribution(found_files, total_blocks)}")
    
    if progress_callback:
        progress_callback(found_files, total_blocks)
    
    return found_files, total_blocks


def main():
    """
    Função principal do programa.
    """
    if len(sys.argv) < 2:
        print("Uso: python file_rescuer.py <caminho_do_dispositivo> [diretório_saída]")
        print("\nExemplos:")
        print("  Windows: python file_rescuer.py E:\\")
        print("  Linux:   python file_rescuer.py /dev/sdb1")
        print("  Com diretório customizado: python file_rescuer.py E:\\ ./minhas_imagens")
        sys.exit(1)
    
    device_path = sys.argv[1]
    output_directory = sys.argv[2] if len(sys.argv) > 2 else "rescued_files"
    
    # Verifica se o dispositivo existe
    if not os.path.exists(device_path):
        print(f"Erro: O caminho '{device_path}' não existe.")
        sys.exit(1)
    
    # Executa a varredura
    found_files, total_blocks = scan_device(device_path, output_directory)
    
    if found_files == 0:
        print("\nNenhum arquivo de imagem válido foi encontrado.")
    else:
        print(f"\n{found_files} arquivo(s) recuperado(s) com sucesso!")


if __name__ == "__main__":
    main()

