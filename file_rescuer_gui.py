#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
File Rescuer GUI - Interface gráfica moderna e clean
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import os
import platform
import shutil
from pathlib import Path
from file_rescuer import scan_device, scan_device_videos, analyze_data_distribution


class FileRescuerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("File Rescuer")
        self.root.geometry("800x750")
        self.root.resizable(True, True)
        
        # Cores modernas
        self.colors = {
            'bg': '#f5f5f5',
            'primary': '#2196F3',
            'success': '#4CAF50',
            'danger': '#f44336',
            'warning': '#FF9800',
            'text': '#212121',
            'text_light': '#757575',
            'border': '#e0e0e0'
        }
        
        self.root.configure(bg=self.colors['bg'])
        
        # Variáveis
        self.device_path = tk.StringVar()
        self.output_directory = tk.StringVar(value="rescued_files")
        self.recovery_mode = tk.StringVar(value="images")
        self.is_scanning = False
        self.found_files = 0
        self.total_blocks = 0
        
        # Flag de cancelamento
        class CancelFlag:
            def __init__(self):
                self.cancelled = False
        self.cancel_flag = CancelFlag()
        
        self.create_widgets()
        
    def create_widgets(self):
        # Header
        header = tk.Frame(self.root, bg=self.colors['primary'], pady=15)
        header.pack(fill=tk.X)
        
        title = tk.Label(
            header,
            text="File Rescuer",
            font=("Segoe UI", 20, "bold"),
            bg=self.colors['primary'],
            fg="white"
        )
        title.pack()
        
        subtitle = tk.Label(
            header,
            text="Recuperação de Imagens e Vídeos",
            font=("Segoe UI", 10),
            bg=self.colors['primary'],
            fg="white"
        )
        subtitle.pack()
        
        # Container principal
        container = tk.Frame(self.root, bg=self.colors['bg'], padx=20, pady=15)
        container.pack(fill=tk.BOTH, expand=True)
        
        # Dispositivo
        self.create_section(container, "Dispositivo", 0)
        device_frame = self.sections[0]
        
        # Lista de dispositivos
        devices_label = tk.Label(device_frame, text="Dispositivos:", font=("Segoe UI", 9), bg=self.colors['bg'])
        devices_label.pack(anchor=tk.W, pady=(0, 5))
        
        list_frame = tk.Frame(device_frame, bg=self.colors['bg'])
        list_frame.pack(fill=tk.X, pady=(0, 10))
        
        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.devices_listbox = tk.Listbox(
            list_frame,
            height=4,
            font=("Segoe UI", 9),
            yscrollcommand=scrollbar.set,
            bg="white",
            relief=tk.FLAT,
            borderwidth=1
        )
        self.devices_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.devices_listbox.yview)
        self.devices_listbox.bind('<<ListboxSelect>>', self.on_device_select)
        
        # Botões de dispositivo
        device_buttons = tk.Frame(device_frame, bg=self.colors['bg'])
        device_buttons.pack(fill=tk.X, pady=(0, 10))
        
        tk.Button(
            device_buttons,
            text="Atualizar",
            command=self.refresh_devices,
            font=("Segoe UI", 9),
            bg=self.colors['primary'],
            fg="white",
            relief=tk.FLAT,
            padx=15,
            pady=5,
            cursor="hand2"
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        tk.Button(
            device_buttons,
            text="Procurar MTP",
            command=self.browse_mtp_device,
            font=("Segoe UI", 9),
            bg=self.colors['warning'],
            fg="white",
            relief=tk.FLAT,
            padx=15,
            pady=5,
            cursor="hand2"
        ).pack(side=tk.LEFT)
        
        # Campo manual
        tk.Label(device_frame, text="Ou digite manualmente:", font=("Segoe UI", 9), bg=self.colors['bg']).pack(anchor=tk.W, pady=(5, 0))
        
        entry_frame = tk.Frame(device_frame, bg=self.colors['bg'])
        entry_frame.pack(fill=tk.X, pady=(5, 0))
        
        self.device_entry = tk.Entry(entry_frame, textvariable=self.device_path, font=("Segoe UI", 9), relief=tk.FLAT, borderwidth=1)
        self.device_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        # Modo de recuperação
        self.create_section(container, "Modo de Recuperação", 1)
        mode_frame = self.sections[1]
        
        tk.Radiobutton(
            mode_frame,
            text="Imagens (JPEG, PNG)",
            variable=self.recovery_mode,
            value="images",
            font=("Segoe UI", 10),
            bg=self.colors['bg'],
            activebackground=self.colors['bg']
        ).pack(anchor=tk.W, pady=2)
        
        tk.Radiobutton(
            mode_frame,
            text="Vídeos (MP4, AVI, MKV, FLV, MOV)",
            variable=self.recovery_mode,
            value="videos",
            font=("Segoe UI", 10),
            bg=self.colors['bg'],
            activebackground=self.colors['bg']
        ).pack(anchor=tk.W, pady=2)
        
        # Diretório de saída
        self.create_section(container, "Diretório de Saída", 2)
        output_frame = self.sections[2]
        
        output_entry_frame = tk.Frame(output_frame, bg=self.colors['bg'])
        output_entry_frame.pack(fill=tk.X)
        
        self.output_entry = tk.Entry(output_entry_frame, textvariable=self.output_directory, font=("Segoe UI", 9), relief=tk.FLAT, borderwidth=1)
        self.output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        tk.Button(
            output_entry_frame,
            text="Procurar",
            command=self.browse_output,
            font=("Segoe UI", 9),
            bg=self.colors['primary'],
            fg="white",
            relief=tk.FLAT,
            padx=15,
            pady=5,
            cursor="hand2"
        ).pack(side=tk.RIGHT)
        
        # Botões de ação
        action_frame = tk.Frame(container, bg=self.colors['bg'])
        action_frame.pack(fill=tk.X, pady=(10, 0))
        
        self.scan_button = tk.Button(
            action_frame,
            text="Iniciar Varredura",
            command=self.start_scan,
            font=("Segoe UI", 11, "bold"),
            bg=self.colors['success'],
            fg="white",
            relief=tk.FLAT,
            padx=25,
            pady=10,
            cursor="hand2"
        )
        self.scan_button.pack(side=tk.LEFT, padx=(0, 10))
        
        self.stop_button = tk.Button(
            action_frame,
            text="Parar",
            command=self.stop_scan,
            font=("Segoe UI", 11, "bold"),
            bg=self.colors['danger'],
            fg="white",
            relief=tk.FLAT,
            padx=25,
            pady=10,
            state=tk.DISABLED,
            cursor="hand2"
        )
        self.stop_button.pack(side=tk.LEFT)
        
        # Progresso
        self.create_section(container, "Progresso", 3)
        progress_frame = self.sections[3]
        
        self.progress_label = tk.Label(
            progress_frame,
            text="Pronto para iniciar",
            font=("Segoe UI", 9),
            bg=self.colors['bg']
        )
        self.progress_label.pack(anchor=tk.W, pady=(0, 5))
        
        self.progress_bar = ttk.Progressbar(
            progress_frame,
            mode='indeterminate',
            length=400
        )
        self.progress_bar.pack(fill=tk.X)
        
        # Estatísticas
        self.stats_text = tk.Label(
            progress_frame,
            text="Blocos: 0 | Arquivos: 0 | Estado: Aguardando...",
            font=("Segoe UI", 9),
            bg=self.colors['bg'],
            fg=self.colors['text_light']
        )
        self.stats_text.pack(anchor=tk.W, pady=(5, 0))
        
        # Log
        self.create_section(container, "Log", 4)
        log_frame = self.sections[4]
        
        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            height=8,
            font=("Consolas", 8),
            wrap=tk.WORD,
            bg="white",
            relief=tk.FLAT,
            borderwidth=1
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        self.log("Sistema iniciado. Selecione um dispositivo e clique em 'Iniciar Varredura'.")
        
        self.root.after(100, self.refresh_devices)
    
    def create_section(self, parent, title, index):
        """Cria uma seção com título"""
        if not hasattr(self, 'sections'):
            self.sections = []
        
        frame = tk.LabelFrame(
            parent,
            text=title,
            font=("Segoe UI", 10, "bold"),
            bg=self.colors['bg'],
            fg=self.colors['text'],
            padx=10,
            pady=10,
            relief=tk.FLAT,
            borderwidth=1
        )
        frame.pack(fill=tk.X, pady=(0, 10))
        self.sections.append(frame)
        return frame
    
    def get_available_devices(self):
        """Retorna lista de dispositivos disponíveis"""
        devices = []
        
        if platform.system() == 'Windows':
            try:
                import string
                import ctypes
                
                bitmask = ctypes.windll.kernel32.GetLogicalDrives()
                for letter in string.ascii_uppercase:
                    if bitmask & 1:
                        drive = f"{letter}:\\"
                        if os.path.exists(drive):
                            try:
                                total, used, free = shutil.disk_usage(drive)
                                total_gb = total / (1024**3)
                                free_gb = free / (1024**3)
                                
                                volume_name = ""
                                try:
                                    volume_name_buffer = ctypes.create_unicode_buffer(1024)
                                    ctypes.windll.kernel32.GetVolumeInformationW(
                                        drive, volume_name_buffer, 1024, None, None, None, None, 0
                                    )
                                    volume_name = volume_name_buffer.value
                                except:
                                    pass
                                
                                drive_type = ctypes.windll.kernel32.GetDriveTypeW(drive)
                                type_names = {2: "Removível", 3: "Disco Local", 4: "Rede", 5: "CD-ROM"}
                                device_type = type_names.get(drive_type, "Desconhecido")
                                
                                if volume_name:
                                    display_name = f"{drive} [{volume_name}] | {device_type} | {free_gb:.1f} GB livres"
                                else:
                                    display_name = f"{drive} | {device_type} | {free_gb:.1f} GB livres"
                                
                                raw_path = f"\\\\.\\{letter}:"
                                devices.append((display_name, raw_path, device_type))
                            except:
                                pass
                    bitmask >>= 1
            except:
                pass
        else:
            try:
                import glob
                for device in glob.glob("/dev/sd*"):
                    if os.path.exists(device):
                        devices.append((device, device, "Disco"))
            except:
                pass
        
        return devices
    
    def refresh_devices(self):
        """Atualiza lista de dispositivos"""
        try:
            if not hasattr(self, 'devices_listbox'):
                return
            
            self.devices_listbox.delete(0, tk.END)
            self.log("Procurando dispositivos...")
            
            devices = self.get_available_devices()
            
            if devices:
                for display_name, raw_path, device_type in devices:
                    self.devices_listbox.insert(tk.END, display_name)
                self.log(f"Encontrados {len(devices)} dispositivo(s).")
            else:
                self.devices_listbox.insert(tk.END, "Nenhum dispositivo encontrado")
                self.log("Nenhum dispositivo encontrado.")
        except Exception as e:
            pass
    
    def on_device_select(self, event):
        """Chamado quando dispositivo é selecionado"""
        selection = self.devices_listbox.curselection()
        if selection:
            index = selection[0]
            devices = self.get_available_devices()
            if index < len(devices):
                display_name, raw_path, device_type = devices[index]
                self.device_path.set(raw_path)
                self.log(f"Dispositivo selecionado: {display_name}")
    
    def browse_mtp_device(self):
        """Abre diálogo para MTP"""
        if platform.system() == 'Windows':
            try:
                import subprocess
                subprocess.Popen(['explorer', 'shell:::{20D04FE0-3AEA-1069-A2D8-08002B30309D}'])
                
                path = filedialog.askdirectory(
                    title="Selecione a pasta do seu celular Android"
                )
                
                if path:
                    self.device_path.set(path)
                    self.log(f"Dispositivo MTP selecionado: {path}")
            except Exception as e:
                messagebox.showerror("Erro", f"Erro: {str(e)}")
    
    def browse_output(self):
        """Abre diálogo para diretório de saída"""
        path = filedialog.askdirectory(title="Selecione o diretório de saída")
        if path:
            self.output_directory.set(path)
    
    def log(self, message):
        """Adiciona mensagem ao log"""
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()
    
    def start_scan(self):
        """Inicia varredura"""
        device = self.device_path.get().strip()
        output = self.output_directory.get().strip()
        
        if not device:
            messagebox.showerror("Erro", "Selecione um dispositivo!")
            return
        
        if not output:
            messagebox.showerror("Erro", "Selecione um diretório de saída!")
            return
        
        # Valida caminho
        if platform.system() == 'Windows':
            if device.startswith('\\\\.\\'):
                drive_letter = device[4] if len(device) >= 6 else None
                if drive_letter:
                    normal_path = f"{drive_letter}:\\"
                    if not os.path.exists(normal_path):
                        messagebox.showerror("Erro", f"Unidade '{drive_letter}:' não existe!")
                        return
            elif not os.path.exists(device):
                messagebox.showerror("Erro", f"Caminho '{device}' não existe!")
                return
        else:
            if not os.path.exists(device):
                messagebox.showerror("Erro", f"Caminho '{device}' não existe!")
                return
        
        # Ajusta diretório de saída
        mode = self.recovery_mode.get()
        if not output or output == "rescued_files":
            if mode == "videos":
                self.output_directory.set("rescued_videos")
                output = "rescued_videos"
            else:
                self.output_directory.set("rescued_files")
                output = "rescued_files"
        
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
        
        mode_text = "vídeos" if mode == "videos" else "imagens"
        self.progress_label.config(text=f"Varredura de {mode_text} em andamento...")
        self.log_text.delete(1.0, tk.END)
        self.log(f"Iniciando varredura de {mode_text}...")
        self.log(f"Dispositivo: {device}")
        self.log(f"Saída: {output}")
        self.log("-" * 60)
        
        # Inicia thread
        scan_thread = threading.Thread(
            target=self.scan_thread_worker,
            args=(device, output, mode),
            daemon=True
        )
        scan_thread.start()
    
    def scan_thread_worker(self, device_path, output_directory, mode):
        """Worker thread para varredura"""
        try:
            self.found_files = 0
            self.total_blocks = 0
            self.cancel_flag.cancelled = False
            
            # Callback de progresso - atualiza a cada bloco
            def progress_callback(found, blocks):
                if not self.cancel_flag.cancelled:
                    self.found_files = found
                    self.total_blocks = blocks
                    # Força atualização imediata da UI
                    self.root.after(0, self.update_progress)
            
            # Callback de log
            def log_callback(message):
                self.root.after(0, lambda: self.log(message))
            
            # Executa varredura
            if mode == "videos":
                found, blocks = scan_device_videos(
                    device_path,
                    output_directory,
                    progress_callback=progress_callback,
                    log_callback=log_callback,
                    cancel_flag=self.cancel_flag
                )
            else:
                found, blocks = scan_device(
                    device_path,
                    output_directory,
                    progress_callback=progress_callback,
                    log_callback=log_callback,
                    cancel_flag=self.cancel_flag
                )
            
            if not self.cancel_flag.cancelled:
                self.found_files = found
                self.total_blocks = blocks
                self.root.after(0, self.scan_completed)
            else:
                self.root.after(0, self.scan_cancelled)
                
        except Exception as e:
            if not self.cancel_flag.cancelled:
                self.root.after(0, lambda: self.scan_error(str(e)))
    
    def update_progress(self):
        """Atualiza progresso na UI"""
        status = analyze_data_distribution(self.found_files, self.total_blocks)
        self.stats_text.config(
            text=f"Blocos: {self.total_blocks} | Arquivos: {self.found_files} | {status}"
        )
        mode_text = "vídeos" if self.recovery_mode.get() == "videos" else "imagens"
        self.progress_label.config(
            text=f"Varrendo bloco {self.total_blocks}... ({self.found_files} {mode_text} encontrados)"
        )
    
    def scan_completed(self):
        """Chamado quando varredura completa"""
        self.is_scanning = False
        self.progress_bar.stop()
        self.progress_label.config(text="Varredura concluída!")
        
        status = analyze_data_distribution(self.found_files, self.total_blocks)
        self.stats_text.config(
            text=f"Blocos: {self.total_blocks} | Arquivos: {self.found_files} | {status}"
        )
        
        self.log("-" * 60)
        self.log(f"Varredura concluída!")
        self.log(f"Blocos: {self.total_blocks} | Arquivos: {self.found_files}")
        
        # Restaura interface
        self.scan_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.device_entry.config(state=tk.NORMAL)
        self.output_entry.config(state=tk.NORMAL)
        
        messagebox.showinfo(
            "Concluído",
            f"Varredura finalizada!\n\nArquivos: {self.found_files}\nBlocos: {self.total_blocks}"
        )
    
    def scan_error(self, error_msg):
        """Chamado em caso de erro"""
        self.is_scanning = False
        self.progress_bar.stop()
        self.progress_label.config(text="Erro durante a varredura")
        self.log(f"ERRO: {error_msg}")
        
        self.scan_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.device_entry.config(state=tk.NORMAL)
        self.output_entry.config(state=tk.NORMAL)
        
        messagebox.showerror("Erro", f"Erro durante a varredura:\n\n{error_msg}")
    
    def stop_scan(self):
        """Para varredura"""
        if self.is_scanning:
            self.cancel_flag.cancelled = True
            self.is_scanning = False
            self.log("Parando varredura...")
            self.progress_label.config(text="Parando varredura...")
            self.stop_button.config(state=tk.DISABLED)
    
    def scan_cancelled(self):
        """Chamado quando cancelado"""
        self.is_scanning = False
        self.progress_bar.stop()
        self.progress_label.config(text="Varredura cancelada")
        
        self.stats_text.config(
            text=f"Blocos: {self.total_blocks} | Arquivos: {self.found_files} | Cancelado"
        )
        
        self.log("-" * 60)
        self.log("Varredura cancelada pelo usuário")
        
        self.scan_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.device_entry.config(state=tk.NORMAL)
        self.output_entry.config(state=tk.NORMAL)
        
        messagebox.showinfo(
            "Cancelado",
            f"Varredura interrompida.\n\nArquivos: {self.found_files}\nBlocos: {self.total_blocks}"
        )


def main():
    try:
        root = tk.Tk()
        app = FileRescuerGUI(root)
        root.mainloop()
    except Exception as e:
        import traceback
        error_msg = f"Erro ao iniciar:\n\n{str(e)}\n\n{traceback.format_exc()}"
        try:
            root_error = tk.Tk()
            root_error.withdraw()
            messagebox.showerror("Erro Fatal", error_msg)
            root_error.destroy()
        except:
            print(error_msg)
            input("Pressione Enter para sair...")


if __name__ == "__main__":
    main()
