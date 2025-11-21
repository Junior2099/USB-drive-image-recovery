# File Rescuer 🔍

Programa em Python para recuperar arquivos de imagem (JPEG e PNG) de dispositivos de armazenamento usando Magic Bytes.

## 📋 Funcionalidades

- ✅ Varredura de dispositivos em blocos de 32 MB
- ✅ Identificação de arquivos JPEG e PNG por Magic Bytes
- ✅ Validação de imagens corrompidas usando Pillow (PIL)
- ✅ Análise de distribuição de dados no dispositivo
- ✅ Salvamento automático de arquivos recuperados

## 🚀 Instalação

1. Instale as dependências:
```bash
pip install -r requirements.txt
```

## 💻 Uso

### Interface Gráfica (Recomendado)

Para usar a interface gráfica, execute:

```bash
python file_rescuer_gui.py
```

A interface gráfica oferece:
- ✅ Seleção visual de dispositivo e diretório de saída
- ✅ Barra de progresso em tempo real
- ✅ Log de atividades
- ✅ Estatísticas atualizadas
- ✅ Fácil de usar, sem necessidade de linha de comando

### Linha de Comando (CLI)

#### Sintaxe Básica
```bash
python file_rescuer.py <caminho_do_dispositivo> [diretório_saída]
```

#### Exemplos

**Windows:**
```bash
# IMPORTANTE: Para recuperar arquivos APAGADOS, use o formato raw:
python file_rescuer.py \\.\E:
python file_rescuer.py \\.\E: ./imagens_recuperadas

# Execute como Administrador para ter acesso raw ao dispositivo!
# Se usar apenas E:\, o programa lerá apenas arquivos existentes, não os apagados.
```

**Linux:**
```bash
python file_rescuer.py /dev/sdb1
sudo python file_rescuer.py /dev/sdb1 ./rescued_files
```

**macOS:**
```bash
python file_rescuer.py /dev/disk2s1
```

## 📝 Detalhes Técnicos

### Magic Bytes Suportados

**JPEG:**
- Início (Header): `FF D8`
- Fim (Footer): `FF D9`

**PNG:**
- Início (Header): `89 50 4E 47 0D 0A 1A 0A`
- Fim (Footer): `49 45 4E 44 AE 42 60 82` (IEND chunk)

### Processo de Varredura

1. O dispositivo é lido em blocos de 32 MB
2. Cada bloco é analisado byte a byte procurando pelos Magic Bytes de início
3. Quando um header é encontrado, o programa procura pelo footer correspondente
4. A imagem extraída é validada usando Pillow
5. Imagens válidas são salvas no diretório de saída com nomes únicos

### Análise de Distribuição

O programa classifica o estado do dispositivo baseado na densidade de arquivos encontrados:
- **Vazio ou recém-formatado**: Nenhum arquivo encontrado
- **Parcialmente populado**: Menos de 0.1 arquivo por MB
- **Bem populado**: Entre 0.1 e 1 arquivo por MB
- **Muito populado**: Mais de 1 arquivo por MB

## ⚠️ Avisos Importantes

- **Windows**: Use o caminho da unidade com barra invertida dupla (ex: `E:\\`) ou entre aspas (ex: `"E:\"`)
- **Linux/macOS**: Você pode precisar de permissões de administrador (sudo) para acessar dispositivos raw
- O programa cria automaticamente o diretório de saída se ele não existir
- Arquivos salvos recebem nomes únicos usando timestamp e UUID

## 📦 Estrutura de Arquivos

```
file_rescuer.py      # Programa principal (CLI)
file_rescuer_gui.py  # Interface gráfica (GUI)
requirements.txt     # Dependências
README.md           # Este arquivo
rescued_files/      # Diretório padrão para arquivos recuperados (criado automaticamente)
```

## 🔧 Requisitos

- Python 3.6 ou superior
- Pillow (PIL) >= 10.0.0

## 📄 Licença

Este programa é fornecido como está, sem garantias.

