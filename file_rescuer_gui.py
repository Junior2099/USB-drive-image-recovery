#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
File Rescuer GUI - Interface gráfica para o programa File Rescuer
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import os
from pathlib import Path
from file_rescuer import scan_device, analyze_data_distribution


class FileRescuerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("File Rescuer - Recuperador de Imagens")
        self.root.geometry("700x600")
        self.root.resizable(True, True)
        
        # Variáveis
        self.device_path = tk.StringVar()
        self.output_directory = tk.StringVar(value="rescued_files")
        self.is_scanning = False
        self.found_files = 0
        self.total_blocks = 0
        
        self.create_widgets()
        
    def create_widgets(self):
        # Título
        title_frame = tk.Frame(self.root, bg="#2c3e50", pady=20)
        title_frame.pack(fill=tk.X)
        
        title_label = tk.Label(
            title_frame,
            text="🔍 File Rescuer",
            font=("Arial", 24, "bold"),
            bg="#2c3e50",
            fg="white"
        )
        title_label.pack()
        
        subtitle_label = tk.Label(
            title_frame,
            text="Recuperador de Imagens por Magic Bytes",
            font=("Arial", 10),
            bg="#2c3e50",
            fg="#ecf0f1"
        )
        subtitle_label.pack()
        
        # Frame principal
        main_frame = tk.Frame(self.root, padx=20, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Seleção de dispositivo
        device_frame = tk.LabelFrame(main_frame, text="Dispositivo de Armazenamento", padx=10, pady=10)
        device_frame.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(device_frame, text="Caminho do dispositivo:").pack(anchor=tk.W)
        
        device_entry_frame = tk.Frame(device_frame)
        device_entry_frame.pack(fill=tk.X, pady=(5, 0))
        
        self.device_entry = tk.Entry(device_entry_frame, textvariable=self.device_path, font=("Arial", 10))
        self.device_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        tk.Button(
            device_entry_frame,
            text="Procurar...",
            command=self.browse_device,
            width=12
        ).pack(side=tk.RIGHT)
        
        # Dica
        import platform
        if platform.system() == 'Windows':
            tip_text = "IMPORTANTE: Para recuperar arquivos apagados, use: \\\\.\\E: (onde E: é sua unidade)\nExecute como Administrador!"
        else:
            tip_text = "Exemplo: /dev/sdb1 (execute com sudo para acesso raw)"
        
        tip_label = tk.Label(
            device_frame,
            text=tip_text,
            font=("Arial", 8),
            fg="red" if platform.system() == 'Windows' else "gray",
            wraplength=600
        )
        tip_label.pack(anchor=tk.W, pady=(5, 0))
        
        # Diretório de saída
        output_frame = tk.LabelFrame(main_frame, text="Diretório de Saída", padx=10, pady=10)
        output_frame.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(output_frame, text="Onde salvar os arquivos recuperados:").pack(anchor=tk.W)
        
        output_entry_frame = tk.Frame(output_frame)
        output_entry_frame.pack(fill=tk.X, pady=(5, 0))
        
        self.output_entry = tk.Entry(output_entry_frame, textvariable=self.output_directory, font=("Arial", 10))
        self.output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        tk.Button(
            output_entry_frame,
            text="Procurar...",
            command=self.browse_output,
            width=12
        ).pack(side=tk.RIGHT)
        
        # Botões de ação
        button_frame = tk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.scan_button = tk.Button(
            button_frame,
            text="▶ Iniciar Varredura",
            command=self.start_scan,
            bg="#27ae60",
            fg="white",
            font=("Arial", 12, "bold"),
            padx=20,
            pady=10,
            cursor="hand2"
        )
        self.scan_button.pack(side=tk.LEFT, padx=(0, 10))
        
        self.stop_button = tk.Button(
            button_frame,
            text="⏹ Parar",
            command=self.stop_scan,
            bg="#e74c3c",
            fg="white",
            font=("Arial", 12, "bold"),
            padx=20,
            pady=10,
            state=tk.DISABLED,
            cursor="hand2"
        )
        self.stop_button.pack(side=tk.LEFT)
        
        # Barra de progresso
        progress_frame = tk.LabelFrame(main_frame, text="Progresso", padx=10, pady=10)
        progress_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.progress_label = tk.Label(
            progress_frame,
            text="Pronto para iniciar",
            font=("Arial", 10)
        )
        self.progress_label.pack(anchor=tk.W, pady=(0, 5))
        
        self.progress_bar = ttk.Progressbar(
            progress_frame,
            mode='indeterminate',
            length=400
        )
        self.progress_bar.pack(fill=tk.X)
        
        # Estatísticas
        stats_frame = tk.LabelFrame(main_frame, text="Estatísticas", padx=10, pady=10)
        stats_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.stats_text = tk.Label(
            stats_frame,
            text="Blocos varridos: 0\nArquivos encontrados: 0\nEstado: Aguardando...",
            font=("Arial", 10),
            justify=tk.LEFT
        )
        self.stats_text.pack(anchor=tk.W)
        
        # Área de log
        log_frame = tk.LabelFrame(main_frame, text="Log de Atividades", padx=10, pady=10)
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            height=10,
            font=("Consolas", 9),
            wrap=tk.WORD
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        self.log("Sistema iniciado. Selecione um dispositivo e clique em 'Iniciar Varredura'.")
        
    def browse_device(self):
        """Abre diálogo para selecionar dispositivo (diretório)"""
        import platform
        if platform.system() == 'Windows':
            # No Windows, mostra instruções sobre formato raw
            messagebox.showinfo(
                "Formato do Dispositivo - Windows",
                "Para recuperar arquivos APAGADOS, você precisa:\n\n"
                "1. Executar o programa como ADMINISTRADOR\n"
                "2. Usar o formato: \\\\.\\E:\n"
                "   (onde E: é a letra da sua unidade)\n\n"
                "Exemplos:\n"
                "  - \\\\.\\E: (para unidade E:)\n"
                "  - \\\\.\\F: (para unidade F:)\n\n"
                "Digite manualmente no campo acima.\n\n"
                "NOTA: Se usar apenas E:\\, o programa lerá apenas\n"
                "os arquivos existentes, não os apagados!"
            )
        else:
            messagebox.showinfo(
                "Formato do Dispositivo - Linux",
                "No Linux, digite o caminho do dispositivo raw:\n\n"
                "Exemplos:\n"
                "  - /dev/sdb1 (para partição)\n"
                "  - /dev/sdb (para disco inteiro)\n\n"
                "Nota: Você pode precisar executar com sudo\n"
                "para ter permissões de acesso raw."
            )
    
    def browse_output(self):
        """Abre diálogo para selecionar diretório de saída"""
        path = filedialog.askdirectory(title="Selecione o diretório de saída")
        if path:
            self.output_directory.set(path)
    
    def log(self, message):
        """Adiciona mensagem ao log"""
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()
    
    def start_scan(self):
        """Inicia a varredura em uma thread separada"""
        device = self.device_path.get().strip()
        output = self.output_directory.get().strip()
        
        if not device:
            messagebox.showerror("Erro", "Por favor, selecione um dispositivo!")
            return
        
        if not output:
            messagebox.showerror("Erro", "Por favor, selecione um diretório de saída!")
            return
        
        if not os.path.exists(device):
            messagebox.showerror("Erro", f"O caminho '{device}' não existe!")
            return
        
        # Cria diretório de saída se não existir
        Path(output).mkdir(parents=True, exist_ok=True)
        
        self.is_scanning = True
        self.found_files = 0
        self.total_blocks = 0
        
        # Atualiza interface
        self.scan_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.device_entry.config(state=tk.DISABLED)
        self.output_entry.config(state=tk.DISABLED)
        self.progress_bar.start()
        self.progress_label.config(text="Varredura em andamento...")
        self.log_text.delete(1.0, tk.END)
        self.log(f"Iniciando varredura do dispositivo: {device}")
        self.log(f"Diretório de saída: {output}")
        self.log("-" * 60)
        
        # Inicia varredura em thread separada
        scan_thread = threading.Thread(
            target=self.scan_thread_worker,
            args=(device, output),
            daemon=True
        )
        scan_thread.start()
    
    def scan_thread_worker(self, device_path, output_directory):
        """Worker thread para executar a varredura"""
        try:
            # Redefine as variáveis de controle
            self.found_files = 0
            self.total_blocks = 0
            
            # Callback para atualizar progresso
            def progress_callback(found, blocks):
                self.found_files = found
                self.total_blocks = blocks
                self.root.after(0, self.update_progress)
            
            # Callback para logging
            def log_callback(message):
                self.root.after(0, lambda: self.log(message))
            
            # Executa a varredura com callbacks
            found, blocks = scan_device(
                device_path,
                output_directory,
                progress_callback=progress_callback,
                log_callback=log_callback
            )
            
            self.found_files = found
            self.total_blocks = blocks
            
            # Atualiza UI na thread principal
            self.root.after(0, self.scan_completed)
            
        except Exception as e:
            self.root.after(0, lambda: self.scan_error(str(e)))
    
    def update_progress(self):
        """Atualiza a interface com o progresso atual"""
        status = analyze_data_distribution(self.found_files, self.total_blocks)
        stats_msg = (
            f"Blocos varridos: {self.total_blocks}\n"
            f"Arquivos encontrados: {self.found_files}\n"
            f"Estado: {status}"
        )
        self.stats_text.config(text=stats_msg)
        self.progress_label.config(text=f"Varrendo bloco {self.total_blocks}... ({self.found_files} arquivos encontrados)")
    
    def scan_completed(self):
        """Chamado quando a varredura é concluída"""
        self.is_scanning = False
        self.progress_bar.stop()
        self.progress_label.config(text="Varredura concluída!")
        
        # Atualiza estatísticas
        status = analyze_data_distribution(self.found_files, self.total_blocks)
        stats_msg = (
            f"Blocos varridos: {self.total_blocks}\n"
            f"Arquivos encontrados: {self.found_files}\n"
            f"Estado: {status}"
        )
        self.stats_text.config(text=stats_msg)
        
        self.log("-" * 60)
        self.log(f"Varredura concluída!")
        self.log(f"Blocos varridos: {self.total_blocks}")
        self.log(f"Arquivos encontrados e salvos: {self.found_files}")
        self.log(f"Estado do dispositivo: {status}")
        
        if self.found_files == 0:
            self.log("Nenhum arquivo de imagem válido foi encontrado.")
        else:
            self.log(f"{self.found_files} arquivo(s) recuperado(s) com sucesso!")
        
        # Restaura interface
        self.scan_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.device_entry.config(state=tk.NORMAL)
        self.output_entry.config(state=tk.NORMAL)
        
        messagebox.showinfo(
            "Varredura Concluída",
            f"Varredura finalizada!\n\n"
            f"Arquivos encontrados: {self.found_files}\n"
            f"Blocos varridos: {self.total_blocks}\n"
            f"Estado: {status}"
        )
    
    def scan_error(self, error_msg):
        """Chamado quando ocorre um erro na varredura"""
        self.is_scanning = False
        self.progress_bar.stop()
        self.progress_label.config(text="Erro durante a varredura")
        
        self.log(f"ERRO: {error_msg}")
        
        # Restaura interface
        self.scan_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.device_entry.config(state=tk.NORMAL)
        self.output_entry.config(state=tk.NORMAL)
        
        messagebox.showerror("Erro", f"Ocorreu um erro durante a varredura:\n\n{error_msg}")
    
    def stop_scan(self):
        """Para a varredura (implementação básica)"""
        if self.is_scanning:
            self.is_scanning = False
            self.log("Parando varredura...")
            # Nota: A implementação completa requereria um mecanismo de cancelamento
            # na função scan_device, o que seria mais complexo
            messagebox.showinfo(
                "Aviso",
                "A varredura será interrompida após o bloco atual.\n"
                "Aguarde alguns segundos..."
            )


def main():
    root = tk.Tk()
    app = FileRescuerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()

