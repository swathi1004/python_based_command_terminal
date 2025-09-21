# 🖥️ Python Web Command Terminal

## 📌 Overview
A Python-based command terminal with a **web interface** built using **Streamlit**.  
It allows users to execute system commands, perform file operations, navigate directories, and monitor system resources.

## ✨ Features
- Python backend with command execution engine (`subprocess`)
- Core file operations: `ls`, `cd`, `pwd`, `mkdir`, `rm`, `cp`, `mv`
- Directory navigation with session state
- System monitoring: CPU, memory, disk usage, running processes
- Web interface for command input & output
- Error handling with helpful messages
- Command history tracking
- Real-time output streaming for long-running commands

## 🚀 Tech Stack
- **Python**
- **Streamlit** (web interface)
- **psutil** (system monitoring)

## 🛠️ Setup
```bash
cd python-web-terminal
pip install -r requirements.txt
streamlit run app.py
