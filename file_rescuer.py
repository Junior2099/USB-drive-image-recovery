#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
File Rescuer - Programa para recuperar arquivos de imagem (JPEG e PNG) e vídeos
de dispositivos de armazenamento usando Magic Bytes.
"""

import os
import sys
import uuid
import platform
from datetime import datetime
from pathlib import Path
from typing import Tuple, Optional, List, Dict
from PIL import Image
from io import BytesIO


# Definições dos Magic Bytes - Imagens
JPEG_HEADER = bytes([0xFF, 0xD8])
JPEG_FOOTER = bytes([0xFF, 0xD9])

PNG_HEADER = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])
PNG_FOOTER = bytes([0x49, 0x45, 0x4E, 0x44, 0xAE, 0x42, 0x60, 0x82])  # IEND chunk

# Definições dos Magic Bytes - Vídeos
# MP4/MOV: Começa com ftyp box (00 00 00 ?? 66 74 79 70)
MP4_HEADER_PATTERN = bytes([0x66, 0x74, 0x79, 0x70])  # "ftyp"
MP4_HEADER_PREFIX = bytes([0x00, 0x00, 0x00])  # Tamanho do box (3 bytes, 4º varia)

# AVI: RIFF...AVI 
AVI_HEADER = bytes([0x52, 0x49, 0x46, 0x46])  # "RIFF"
AVI_SUBTYPE = bytes([0x41, 0x56, 0x49, 0x20])  # "AVI " (com espaço)

# MKV: 1A 45 DF A3
MKV_HEADER = bytes([0x1A, 0x45, 0xDF, 0xA3])

# FLV: 46 4C 56 01
FLV_HEADER = bytes([0x46, 0x4C, 0x56, 0x01])  # "FLV" + versão

# Tamanho máximo de vídeo para recuperação (2 GB por segurança)
MAX_VIDEO_SIZE = 2 * 1024 * 1024 * 1024  # 2 GB

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


def find_mp4_header(data: bytes, start_pos: int = 0) -> Optional[int]:
    """
    Encontra o início de um arquivo MP4/MOV procurando pelo padrão ftyp.
    MP4/MOV começa com um box de tamanho variável seguido de "ftyp".
    
    Args:
        data: Buffer de bytes para procurar
        start_pos: Posição inicial para começar a busca
        
    Returns:
        Posição do início do arquivo MP4/MOV ou None se não encontrado
    """
    # Procura por "ftyp" no buffer
    pos = start_pos
    while True:
        ftyp_pos = data.find(MP4_HEADER_PATTERN, pos)
        if ftyp_pos == -1:
            return None
        
        # Verifica se há pelo menos 4 bytes antes (tamanho do box)
        if ftyp_pos >= 4:
            box_start = ftyp_pos - 4
            # Verifica se o tamanho do box é razoável (não zero e não muito grande)
            size_bytes = data[box_start:ftyp_pos]
            if len(size_bytes) == 4:
                # Tamanho do box em big-endian
                box_size = int.from_bytes(size_bytes, byteorder='big')
                # Tamanho razoável: entre 8 bytes (mínimo) e 1 MB
                if 8 <= box_size <= 1024 * 1024:
                    return box_start
        
        # Continua procurando
        pos = ftyp_pos + 1
        if pos >= len(data):
            return None


def find_avi_header(data: bytes, start_pos: int = 0) -> Optional[int]:
    """
    Encontra o início de um arquivo AVI procurando por RIFF seguido de AVI.
    
    Args:
        data: Buffer de bytes para procurar
        start_pos: Posição inicial para começar a busca
        
    Returns:
        Posição do início do arquivo AVI ou None se não encontrado
    """
    pos = start_pos
    while True:
        riff_pos = data.find(AVI_HEADER, pos)
        if riff_pos == -1:
            return None
        
        # Verifica se há espaço suficiente para "AVI " após RIFF + tamanho (4 bytes)
        if riff_pos + 12 <= len(data):
            # Verifica se os próximos 4 bytes após RIFF são um tamanho razoável
            size_bytes = data[riff_pos + 4:riff_pos + 8]
            if len(size_bytes) == 4:
                # Tamanho em little-endian
                file_size = int.from_bytes(size_bytes, byteorder='little')
                # Verifica se o tamanho é razoável (não zero e não muito grande)
                if 12 <= file_size <= 10 * 1024 * 1024 * 1024:  # Até 10 GB
                    # Verifica se tem "AVI " logo após
                    if data[riff_pos + 8:riff_pos + 12] == AVI_SUBTYPE:
                        return riff_pos
        
        # Continua procurando
        pos = riff_pos + 1
        if pos >= len(data):
            return None


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


def validate_video(data: bytes, format: str) -> bool:
    """
    Valida se um vídeo parece estar completo e válido.
    Validação básica baseada em estrutura de arquivo.
    
    Args:
        data: Bytes do vídeo
        format: Formato do vídeo ('mp4', 'avi', 'mkv', 'flv')
        
    Returns:
        True se o vídeo parece válido, False caso contrário
    """
    if not data or len(data) < 16:  # Mínimo de bytes para ser um arquivo válido
        return False
    
    try:
        format_lower = format.lower()
        
        if format_lower in ['mp4', 'mov']:
            # Verifica se começa com box válido e contém "ftyp"
            if data[:4] == b'\x00\x00\x00\x00':
                return False  # Tamanho zero não é válido
            
            # Procura por "ftyp" nos primeiros bytes
            if MP4_HEADER_PATTERN in data[:20]:
                # Verifica se tem tamanho mínimo razoável (pelo menos 1 KB)
                return len(data) >= 1024
        
        elif format_lower == 'avi':
            # Verifica se começa com RIFF e contém AVI
            if data[:4] == AVI_HEADER:
                if len(data) >= 12 and data[8:12] == AVI_SUBTYPE:
                    # Verifica tamanho mínimo
                    return len(data) >= 1024
        
        elif format_lower == 'mkv':
            # Verifica se começa com o header MKV
            if data[:4] == MKV_HEADER:
                return len(data) >= 1024
        
        elif format_lower == 'flv':
            # Verifica se começa com FLV header
            if data[:4] == FLV_HEADER:
                return len(data) >= 1024
        
    except Exception:
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


def save_video_file(data: bytes, format: str, output_directory: str, log_callback=None) -> str:
    """
    Salva um arquivo de vídeo no diretório de saída.
    
    Args:
        data: Bytes do vídeo
        format: Formato do vídeo ('mp4', 'avi', 'mkv', 'flv', 'mov')
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
    
    # Mapeia formato para extensão
    format_lower = format.lower()
    extension_map = {
        'mp4': '.mp4',
        'mov': '.mov',
        'avi': '.avi',
        'mkv': '.mkv',
        'flv': '.flv'
    }
    extension = extension_map.get(format_lower, '.mp4')
    
    filename = f"rescued_video_{timestamp}_{unique_id}{extension}"
    filepath = os.path.join(output_directory, filename)
    
    # Salva o arquivo
    with open(filepath, 'wb') as f:
        f.write(data)
    
    size_mb = len(data) / (1024 * 1024)
    message = f"Vídeo salvo: {filename} ({size_mb:.2f} MB)"
    if log_callback:
        log_callback(message)
    else:
        print(message)
    
    return filename


def scan_device(device_path: str, output_directory: str = "rescued_files", progress_callback=None, log_callback=None, cancel_flag=None) -> Tuple[int, int]:
    """
    Função principal que varre o dispositivo em busca de arquivos de imagem.
    
    Args:
        device_path: Caminho do dispositivo (ex: /dev/sdb1, E:\, etc.)
        output_directory: Diretório onde salvar os arquivos recuperados
        progress_callback: Função opcional chamada com (found_files, total_blocks) para atualizar progresso
        log_callback: Função opcional chamada com mensagens de log
        cancel_flag: Objeto com atributo 'cancelled' para verificar se deve parar
        
    Returns:
        Tupla com (número de arquivos encontrados, número de blocos varridos)
    """
    found_files = 0
    total_blocks = 0
    buffer_overflow = b''  # Buffer para dados que podem estar entre blocos
    pending_file = None  # Armazena arquivo iniciado mas não finalizado
    
    # Função para verificar se foi cancelado
    def is_cancelled():
        if cancel_flag and hasattr(cancel_flag, 'cancelled'):
            return cancel_flag.cancelled
        return False
    
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
    
    # Verifica se o caminho parece ser um diretório normal (não raw) ou MTP
    is_mtp_device = False
    if platform.system() == 'Windows':
        if not raw_device_path.startswith('\\\\.\\') and os.path.isdir(device_path):
            # Verifica se é dispositivo MTP (Android)
            # MTP pode aparecer como caminho sem letra de unidade ou contendo "Este PC"
            device_path_upper = device_path.upper()
            has_drive_letter = len(device_path) >= 2 and device_path[1] == ':' and device_path[0].isalpha()
            
            # Detecta MTP se:
            # 1. Não tem letra de unidade (não começa com X:)
            # 2. OU contém "Este PC" ou "This PC" no caminho
            # 3. OU é um caminho que não parece ser uma unidade de disco tradicional
            if not has_drive_letter or 'Este PC' in device_path or 'This PC' in device_path or '::{' in device_path:
                is_mtp_device = True
                log("AVISO: Detectado dispositivo MTP (Android)")
                log(f"Caminho MTP: {device_path}")
                log("Dispositivos MTP não permitem acesso raw ao armazenamento")
                log("A varredura será feita nos arquivos existentes do diretório")
                log("NOTA: Arquivos completamente apagados podem não ser recuperáveis via MTP")
            else:
                log("AVISO: Você está acessando um diretório, não o dispositivo raw!")
                log("Para recuperar arquivos APAGADOS, use o formato: \\\\.\\E:")
                log("Onde E: é a letra da sua unidade.")
                log("Continuando com acesso ao diretório (apenas arquivos existentes)...")
    
    # Tenta obter o tamanho do dispositivo (apenas se não for MTP)
    if not is_mtp_device:
        device_size = get_device_size(raw_device_path)
    if device_size:
        size_mb = device_size / (1024 * 1024)
        size_gb = device_size / (1024 * 1024 * 1024)
        if size_gb >= 1:
            log(f"Tamanho do dispositivo: {size_gb:.2f} GB ({device_size:,} bytes)")
        else:
            log(f"Tamanho do dispositivo: {size_mb:.2f} MB ({device_size:,} bytes)")
    
    try:
        # Se é dispositivo MTP, usa abordagem diferente - varre arquivos do diretório
        if is_mtp_device:
            log("Iniciando varredura de arquivos em dispositivo MTP...")
            log("Varredura recursiva de arquivos existentes...")
            
            # Varre recursivamente os arquivos no diretório MTP
            import os
            from pathlib import Path
            
            def scan_mtp_directory(directory, found_files, total_files_scanned):
                """Varre recursivamente um diretório MTP procurando por imagens"""
                try:
                    log(f"Varrendo diretório MTP: {directory}")
                    file_count = 0
                    for root, dirs, files in os.walk(directory):
                        # Verifica cancelamento
                        if is_cancelled():
                            log("Varredura cancelada pelo usuário.")
                            return
                        
                        for file in files:
                            # Verifica cancelamento
                            if is_cancelled():
                                log("Varredura cancelada pelo usuário.")
                                return
                            
                            file_count += 1
                            total_files_scanned[0] += 1
                            
                            if total_files_scanned[0] % 100 == 0:
                                log(f"Verificados {total_files_scanned[0]} arquivos... Encontrados {found_files[0]} imagens")
                                if progress_callback:
                                    progress_callback(found_files[0], total_files_scanned[0] // 100)
                            
                            file_path = os.path.join(root, file)
                            try:
                                # Verifica extensão primeiro para ser mais rápido
                                file_lower = file.lower()
                                is_image_file = file_lower.endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp'))
                                
                                # Tenta ler o arquivo
                                with open(file_path, 'rb') as f:
                                    # Lê apenas os primeiros bytes para verificar header
                                    header = f.read(16)
                                    f.seek(0)
                                    
                                    # Verifica se é JPEG
                                    if header.startswith(JPEG_HEADER):
                                        file_data = f.read()
                                        if file_data.endswith(JPEG_FOOTER):
                                            if validate_image(file_data, 'jpeg'):
                                                filename = save_file(file_data, 'jpeg', output_directory, log_callback)
                                                found_files[0] += 1
                                                log(f"Imagem JPEG encontrada: {file}")
                                                if progress_callback:
                                                    progress_callback(found_files[0], total_files_scanned[0] // 100)
                                    
                                    # Verifica se é PNG
                                    elif header.startswith(PNG_HEADER):
                                        file_data = f.read()
                                        if PNG_FOOTER in file_data[-100:]:
                                            if validate_image(file_data, 'png'):
                                                filename = save_file(file_data, 'png', output_directory, log_callback)
                                                found_files[0] += 1
                                                log(f"Imagem PNG encontrada: {file}")
                                                if progress_callback:
                                                    progress_callback(found_files[0], total_files_scanned[0] // 100)
                            except PermissionError:
                                # Ignora arquivos sem permissão
                                pass
                            except Exception as e:
                                # Ignora outros erros de leitura
                                pass
                    
                    log(f"Total de arquivos no diretório: {file_count}")
                except Exception as e:
                    log(f"Erro ao varrer diretório MTP: {e}")
                    import traceback
                    log(f"Detalhes: {traceback.format_exc()}")
            
            found_files_list = [0]
            total_files_scanned = [0]
            scan_mtp_directory(device_path, found_files_list, total_files_scanned)
            
            found_files = found_files_list[0]
            total_blocks = total_files_scanned[0] // 100  # Aproximação para compatibilidade
            
            log(f"\n{'=' * 60}")
            log(f"Varredura MTP concluída!")
            log(f"Arquivos verificados: {total_files_scanned[0]}")
            log(f"Imagens encontradas e salvas: {found_files}")
            
            if progress_callback:
                progress_callback(found_files, total_blocks)
            
            return found_files, total_blocks
        
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
            consecutive_empty_blocks = 0
            max_empty_blocks = 100  # Limite de blocos vazios consecutivos antes de parar
            
            log("Iniciando leitura do dispositivo...")
            log("Aguarde, a leitura pode demorar dependendo do tamanho do dispositivo...")
            
            # Tenta ler um pequeno bloco primeiro para verificar se o dispositivo está acessível
            try:
                log("Testando acesso ao dispositivo (lendo 1 MB)...")
                test_block = device.read(1024 * 1024)  # Lê 1 MB primeiro para testar
                if not test_block:
                    log("AVISO: Dispositivo parece estar vazio ou inacessível")
                    device.close()
                    return found_files, total_blocks
                log(f"Teste OK! Dispositivo acessível. Lidos {len(test_block)} bytes.")
                # Volta para o início do arquivo
                device.seek(0)
                log("Reiniciando leitura do início do dispositivo...")
            except Exception as e:
                log(f"ERRO: Não foi possível ler do dispositivo: {e}")
                import traceback
                log(f"Detalhes: {traceback.format_exc()}")
                try:
                    device.close()
                except:
                    pass
                return found_files, total_blocks
            
            while True:
                # Verifica se foi cancelado
                if is_cancelled():
                    log("Varredura cancelada pelo usuário.")
                    break
                
                # Lê um bloco de 32 MB
                try:
                    # Log apenas no primeiro bloco e depois a cada 10 blocos
                    if total_blocks == 0:
                        log(f"Lendo primeiro bloco completo (32 MB)... Isso pode demorar alguns segundos em dispositivos lentos...")
                    block = device.read(BLOCK_SIZE)
                except Exception as e:
                    log(f"Erro ao ler bloco {total_blocks + 1}: {e}")
                    import traceback
                    log(f"Detalhes: {traceback.format_exc()}")
                    break
                
                # Verifica cancelamento após ler o bloco
                if is_cancelled():
                    log("Varredura cancelada pelo usuário.")
                    break
                
                if not block:
                    consecutive_empty_blocks += 1
                    if consecutive_empty_blocks >= max_empty_blocks:
                        log(f"Lidos {consecutive_empty_blocks} blocos vazios consecutivos. Finalizando varredura.")
                        break
                    # Processa arquivo pendente antes de sair
                    if pending_file:
                        file_data, found_format = pending_file
                        if validate_image(file_data, found_format):
                            filename = save_file(file_data, found_format, output_directory, log_callback)
                            found_files += 1
                            if progress_callback:
                                progress_callback(found_files, total_blocks)
                    # Continua tentando ler mais blocos
                    total_blocks += 1
                    if progress_callback:
                        progress_callback(found_files, total_blocks)
                    continue
                
                consecutive_empty_blocks = 0  # Reset contador se leu dados
                bytes_read_total += len(block)
                
                total_blocks += 1
                
                # Log a cada 10 blocos para mostrar progresso
                if total_blocks % 10 == 0:
                    mb_read = bytes_read_total / (1024 * 1024)
                    log(f"Bloco {total_blocks} lido ({mb_read:.1f} MB processados, {found_files} imagens encontradas)")
                
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
    log(f"Bytes lidos: {bytes_read_total:,} ({bytes_read_total / (1024*1024):.1f} MB)")
    log(f"Arquivos encontrados e salvos: {found_files}")
    log(f"Estado do dispositivo: {analyze_data_distribution(found_files, total_blocks)}")
    
    if progress_callback:
        progress_callback(found_files, total_blocks)
    
    return found_files, total_blocks


def scan_device_videos(device_path: str, output_directory: str = "rescued_videos", progress_callback=None, log_callback=None, cancel_flag=None) -> Tuple[int, int]:
    """
    Função separada que varre o dispositivo em busca de arquivos de vídeo.
    
    Args:
        device_path: Caminho do dispositivo (ex: /dev/sdb1, E:\, etc.)
        output_directory: Diretório onde salvar os arquivos recuperados
        progress_callback: Função opcional chamada com (found_files, total_blocks) para atualizar progresso
        log_callback: Função opcional chamada com mensagens de log
        cancel_flag: Objeto com atributo 'cancelled' para verificar se deve parar
        
    Returns:
        Tupla com (número de arquivos encontrados, número de blocos varridos)
    """
    found_files = 0
    total_blocks = 0
    buffer_overflow = b''  # Buffer para dados que podem estar entre blocos
    pending_video = None  # Vídeo iniciado mas não finalizado (dados, formato)
    
    # Função para verificar se foi cancelado
    def is_cancelled():
        if cancel_flag and hasattr(cancel_flag, 'cancelled'):
            return cancel_flag.cancelled
        return False
    
    def log(message):
        if log_callback:
            log_callback(message)
        else:
            print(message)
    
    log(f"Iniciando varredura de vídeos do dispositivo: {device_path}")
    log(f"Diretório de saída: {output_directory}")
    log("-" * 60)
    
    # Converte para caminho raw se necessário
    raw_device_path = get_raw_device_path(device_path)
    
    if raw_device_path != device_path:
        log(f"Convertendo caminho para formato raw: {device_path} -> {raw_device_path}")
    
    # Verifica se o caminho parece ser um diretório normal (não raw) ou MTP
    is_mtp_device = False
    if platform.system() == 'Windows':
        if not raw_device_path.startswith('\\\\.\\') and os.path.isdir(device_path):
            # Verifica se é dispositivo MTP (Android) - não tem letra de unidade ou contém "Este PC"
            if ':' not in device_path or ('Este PC' in device_path or 'This PC' in device_path):
                is_mtp_device = True
                log("AVISO: Detectado dispositivo MTP (Android)")
                log("Dispositivos MTP não permitem acesso raw")
                log("A varredura será feita nos arquivos existentes do diretório")
            else:
                log("AVISO: Você está acessando um diretório, não o dispositivo raw!")
                log("Para recuperar arquivos APAGADOS, use o formato: \\\\.\\E:")
                log("Onde E: é a letra da sua unidade.")
                log("Continuando com acesso ao diretório (apenas arquivos existentes)...")
    
    # Tenta obter o tamanho do dispositivo (apenas se não for MTP)
    if not is_mtp_device:
        device_size = get_device_size(raw_device_path)
        if device_size:
            size_mb = device_size / (1024 * 1024)
            size_gb = device_size / (1024 * 1024 * 1024)
            if size_gb >= 1:
                log(f"Tamanho do dispositivo: {size_gb:.2f} GB ({device_size:,} bytes)")
            else:
                log(f"Tamanho do dispositivo: {size_mb:.2f} MB ({device_size:,} bytes)")
    
    try:
        # Se é dispositivo MTP, usa abordagem diferente - varre arquivos do diretório
        if is_mtp_device:
            log("Iniciando varredura de vídeos em dispositivo MTP...")
            log("Varredura recursiva de arquivos existentes...")
            
            # Varre recursivamente os arquivos no diretório MTP
            import os
            
            def scan_mtp_directory_videos(directory, found_files, total_files_scanned):
                """Varre recursivamente um diretório MTP procurando por vídeos"""
                try:
                    for root, dirs, files in os.walk(directory):
                        # Verifica cancelamento
                        if is_cancelled():
                            log("Varredura cancelada pelo usuário.")
                            return
                        
                        for file in files:
                            # Verifica cancelamento
                            if is_cancelled():
                                log("Varredura cancelada pelo usuário.")
                                return
                            
                            total_files_scanned[0] += 1
                            if total_files_scanned[0] % 100 == 0:
                                if progress_callback:
                                    progress_callback(found_files[0], total_files_scanned[0] // 100)
                            
                            file_path = os.path.join(root, file)
                            try:
                                # Tenta ler o arquivo
                                with open(file_path, 'rb') as f:
                                    file_data = f.read(1024)  # Lê apenas os primeiros bytes para verificar header
                                
                                # Verifica formato de vídeo
                                found_format = None
                                if file_data.startswith(MP4_HEADER_PATTERN) or (len(file_data) >= 4 and file_data[4:8] == MP4_HEADER_PATTERN):
                                    found_format = 'mp4'
                                elif file_data.startswith(AVI_HEADER) and len(file_data) >= 12 and file_data[8:12] == AVI_SUBTYPE:
                                    found_format = 'avi'
                                elif file_data.startswith(MKV_HEADER):
                                    found_format = 'mkv'
                                elif file_data.startswith(FLV_HEADER):
                                    found_format = 'flv'
                                
                                if found_format:
                                    # Lê o arquivo completo
                                    with open(file_path, 'rb') as f:
                                        complete_data = f.read()
                                    
                                    if validate_video(complete_data, found_format):
                                        filename = save_video_file(complete_data, found_format, output_directory, log_callback)
                                        found_files[0] += 1
                                        if progress_callback:
                                            progress_callback(found_files[0], total_files_scanned[0] // 100)
                            except Exception as e:
                                # Ignora erros de leitura de arquivos individuais
                                pass
                except Exception as e:
                    log(f"Erro ao varrer diretório MTP: {e}")
            
            found_files_list = [0]
            total_files_scanned = [0]
            scan_mtp_directory_videos(device_path, found_files_list, total_files_scanned)
            
            found_files = found_files_list[0]
            total_blocks = total_files_scanned[0] // 100  # Aproximação para compatibilidade
            
            log(f"\n{'=' * 60}")
            log(f"Varredura MTP concluída!")
            log(f"Arquivos verificados: {total_files_scanned[0]}")
            log(f"Vídeos encontrados e salvos: {found_files}")
            
            if progress_callback:
                progress_callback(found_files, total_blocks)
            
            return found_files, total_blocks
        
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
            consecutive_empty_blocks = 0
            max_empty_blocks = 100  # Limite de blocos vazios consecutivos antes de parar
            
            log("Iniciando leitura do dispositivo...")
            log("Aguarde, a leitura pode demorar dependendo do tamanho do dispositivo...")
            
            # Tenta ler um pequeno bloco primeiro para verificar se o dispositivo está acessível
            try:
                log("Testando acesso ao dispositivo (lendo 1 MB)...")
                test_block = device.read(1024 * 1024)  # Lê 1 MB primeiro para testar
                if not test_block:
                    log("AVISO: Dispositivo parece estar vazio ou inacessível")
                    device.close()
                    return found_files, total_blocks
                log(f"Teste OK! Dispositivo acessível. Lidos {len(test_block)} bytes.")
                # Volta para o início do arquivo
                device.seek(0)
                log("Reiniciando leitura do início do dispositivo...")
            except Exception as e:
                log(f"ERRO: Não foi possível ler do dispositivo: {e}")
                import traceback
                log(f"Detalhes: {traceback.format_exc()}")
                try:
                    device.close()
                except:
                    pass
                return found_files, total_blocks
            
            while True:
                # Verifica se foi cancelado
                if is_cancelled():
                    log("Varredura cancelada pelo usuário.")
                    break
                
                # Lê um bloco de 32 MB
                try:
                    # Log apenas no primeiro bloco e depois a cada 10 blocos
                    if total_blocks == 0:
                        log(f"Lendo primeiro bloco completo (32 MB)... Isso pode demorar alguns segundos em dispositivos lentos...")
                    block = device.read(BLOCK_SIZE)
                except Exception as e:
                    log(f"Erro ao ler bloco {total_blocks + 1}: {e}")
                    import traceback
                    log(f"Detalhes: {traceback.format_exc()}")
                    break
                
                # Verifica cancelamento após ler o bloco
                if is_cancelled():
                    log("Varredura cancelada pelo usuário.")
                    break
                
                if not block:
                    consecutive_empty_blocks += 1
                    if consecutive_empty_blocks >= max_empty_blocks:
                        log(f"Lidos {consecutive_empty_blocks} blocos vazios consecutivos. Finalizando varredura.")
                        break
                    # Processa vídeo pendente antes de sair
                    if pending_video:
                        video_data, found_format = pending_video
                        if len(video_data) >= 1024 and validate_video(video_data, found_format):
                            filename = save_video_file(video_data, found_format, output_directory, log_callback)
                            found_files += 1
                            if progress_callback:
                                progress_callback(found_files, total_blocks)
                    # Continua tentando ler mais blocos
                    total_blocks += 1
                    if progress_callback:
                        progress_callback(found_files, total_blocks)
                    continue
                
                consecutive_empty_blocks = 0  # Reset contador se leu dados
                bytes_read_total += len(block)
                
                total_blocks += 1
                
                # Log a cada 5 blocos para mostrar progresso mais frequente
                if total_blocks % 5 == 0:
                    mb_read = bytes_read_total / (1024 * 1024)
                    log(f"Bloco {total_blocks} lido ({mb_read:.1f} MB processados, {found_files} vídeos encontrados)")
                
                if log_callback is None:
                    print(f"Varrendo bloco {total_blocks}...", end='\r')
                
                # Atualiza progresso via callback - IMPORTANTE: sempre atualiza, mesmo sem vídeos encontrados
                if progress_callback:
                    progress_callback(found_files, total_blocks)
                
                # Combina o buffer de overflow com o novo bloco
                search_data = buffer_overflow + block
                buffer_overflow = b''
                
                # Se há vídeo pendente, procura pelo próximo header do mesmo tipo
                if pending_video:
                    video_data, found_format = pending_video
                    next_header_pos = None
                    
                    # Procura próximo header do mesmo formato
                    if found_format in ['mp4', 'mov']:
                        next_header_pos = find_mp4_header(search_data, 0)
                    elif found_format == 'avi':
                        next_header_pos = find_avi_header(search_data, 0)
                    elif found_format == 'mkv':
                        next_header_pos = find_magic_bytes(search_data, MKV_HEADER, 0)
                    elif found_format == 'flv':
                        next_header_pos = find_magic_bytes(search_data, FLV_HEADER, 0)
                    
                    if next_header_pos is not None and next_header_pos > 0:
                        # Encontrou próximo header, salva o vídeo anterior
                        complete_video = video_data + search_data[:next_header_pos]
                        if len(complete_video) >= 1024 and validate_video(complete_video, found_format):
                            filename = save_video_file(complete_video, found_format, output_directory, log_callback)
                            found_files += 1
                            if progress_callback:
                                progress_callback(found_files, total_blocks)
                        search_data = search_data[next_header_pos:]
                        pending_video = None
                    elif len(video_data) + len(search_data) >= MAX_VIDEO_SIZE:
                        # Tamanho máximo atingido, salva o que tem
                        if len(video_data) >= 1024 and validate_video(video_data, found_format):
                            filename = save_video_file(video_data, found_format, output_directory, log_callback)
                            found_files += 1
                            if progress_callback:
                                progress_callback(found_files, total_blocks)
                        pending_video = None
                    else:
                        # Footer ainda não encontrado, adiciona mais dados e continua para próximo bloco
                        pending_video = (video_data + search_data, found_format)
                        # Mantém apenas os últimos bytes para próxima busca
                        max_header_len = max(len(MP4_HEADER_PATTERN), len(AVI_HEADER), len(MKV_HEADER), len(FLV_HEADER))
                        if len(search_data) > max_header_len:
                            buffer_overflow = search_data[-max_header_len:]
                        else:
                            buffer_overflow = search_data
                        # Continua para o próximo bloco (não processa mais este bloco)
                        continue
                
                # Procura por novos headers de vídeo
                current_pos = 0
                while current_pos < len(search_data):
                    # Verifica cancelamento durante busca
                    if is_cancelled():
                        log("Varredura cancelada pelo usuário.")
                        break
                    
                    # Procura por diferentes formatos
                    mp4_start = find_mp4_header(search_data, current_pos)
                    avi_start = find_avi_header(search_data, current_pos)
                    mkv_start = find_magic_bytes(search_data, MKV_HEADER, current_pos)
                    flv_start = find_magic_bytes(search_data, FLV_HEADER, current_pos)
                    
                    # Determina qual formato foi encontrado primeiro
                    candidates = []
                    if mp4_start is not None:
                        candidates.append((mp4_start, 'mp4'))
                    if avi_start is not None:
                        candidates.append((avi_start, 'avi'))
                    if mkv_start is not None:
                        candidates.append((mkv_start, 'mkv'))
                    if flv_start is not None:
                        candidates.append((flv_start, 'flv'))
                    
                    if candidates:
                        # Ordena por posição
                        candidates.sort(key=lambda x: x[0])
                        file_start, found_format = candidates[0]
                        
                        # Procura pelo próximo header do mesmo tipo para determinar o fim do vídeo
                        # Por enquanto, inicia como pendente e vai acumulando até encontrar próximo header
                        pending_video = (search_data[file_start:], found_format)
                        # Mantém os últimos bytes que podem conter início de outro arquivo
                        max_header_len = max(len(MP4_HEADER_PATTERN), len(AVI_HEADER), len(MKV_HEADER), len(FLV_HEADER))
                        if len(search_data) > max_header_len:
                            buffer_overflow = search_data[-max_header_len:]
                        break
                    else:
                        break
                
                # Se não há vídeo pendente, mantém os últimos bytes para próxima busca
                if not pending_video and len(search_data) > 0:
                    max_header_len = max(len(MP4_HEADER_PATTERN), len(AVI_HEADER), len(MKV_HEADER), len(FLV_HEADER))
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
    
    # Calcula bytes lidos se disponível
    try:
        bytes_read = bytes_read_total if 'bytes_read_total' in locals() else 0
        if bytes_read > 0:
            log(f"\n{'=' * 60}")
            log(f"Varredura de vídeos concluída!")
            log(f"Blocos varridos: {total_blocks}")
            log(f"Bytes lidos: {bytes_read:,} ({bytes_read / (1024*1024):.1f} MB)")
            log(f"Vídeos encontrados e salvos: {found_files}")
            log(f"Estado do dispositivo: {analyze_data_distribution(found_files, total_blocks)}")
        else:
            log(f"\n{'=' * 60}")
            log(f"Varredura de vídeos concluída!")
            log(f"Blocos varridos: {total_blocks}")
            log(f"Vídeos encontrados e salvos: {found_files}")
            log(f"Estado do dispositivo: {analyze_data_distribution(found_files, total_blocks)}")
    except:
        log(f"\n{'=' * 60}")
        log(f"Varredura de vídeos concluída!")
        log(f"Blocos varridos: {total_blocks}")
        log(f"Vídeos encontrados e salvos: {found_files}")
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

