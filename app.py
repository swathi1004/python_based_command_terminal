import os
import shlex
import shutil
import subprocess
import threading
import queue
import time

import psutil
import streamlit as st

# ---------------------------
# Helper: init session state
# ---------------------------
if "cwd" not in st.session_state:
    st.session_state.cwd = os.getcwd()
if "history" not in st.session_state:
    st.session_state.history = []
if "output" not in st.session_state:
    st.session_state.output = ""
if "running" not in st.session_state:
    st.session_state.running = False

# ---------------------------
# Utility functions
# ---------------------------
def append_output(text):
    st.session_state.output += f"{text}\n"

def run_internal_command(parts):
    """
    Handle core file/directory operations internally for consistent behavior.
    Returns tuple (success_bool, output_or_error_str).
    """
    cmd = parts[0]
    try:
        if cmd == "pwd":
            return True, st.session_state.cwd

        elif cmd == "ls":
            target = parts[1] if len(parts) > 1 else "."
            path = os.path.join(st.session_state.cwd, target)
            items = os.listdir(path)
            return True, "\n".join(items)

        elif cmd == "cd":
            if len(parts) == 1 or parts[1] == "~":
                new_dir = os.path.expanduser("~")
            else:
                new_dir = os.path.join(st.session_state.cwd, parts[1])
            new_dir = os.path.abspath(new_dir)
            if not os.path.exists(new_dir) or not os.path.isdir(new_dir):
                return False, f"cd: no such directory: {parts[1]}"
            st.session_state.cwd = new_dir
            return True, f"Changed directory to {new_dir}"

        elif cmd == "mkdir":
            if len(parts) < 2:
                return False, "Usage: mkdir <dirname>"
            for d in parts[1:]:
                path = os.path.join(st.session_state.cwd, d)
                os.mkdir(path)
            return True, "Directory(ies) created."

        elif cmd == "rm":
            if len(parts) < 2:
                return False, "Usage: rm <file_or_dir>"
            msgs = []
            for target in parts[1:]:
                path = os.path.join(st.session_state.cwd, target)
                if not os.path.exists(path):
                    msgs.append(f"rm: no such file or directory: {target}")
                else:
                    if os.path.isdir(path) and not os.path.islink(path):
                        shutil.rmtree(path)
                        msgs.append(f"Removed directory {target}")
                    else:
                        os.remove(path)
                        msgs.append(f"Removed file {target}")
            return True, "\n".join(msgs)

        elif cmd == "cp":
            if len(parts) < 3:
                return False, "Usage: cp <source> <dest>"
            src = os.path.join(st.session_state.cwd, parts[1])
            dst = os.path.join(st.session_state.cwd, parts[2])
            if os.path.isdir(src):
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
            return True, "Copy completed."

        elif cmd == "mv":
            if len(parts) < 3:
                return False, "Usage: mv <source> <dest>"
            src = os.path.join(st.session_state.cwd, parts[1])
            dst = os.path.join(st.session_state.cwd, parts[2])
            shutil.move(src, dst)
            return True, "Move/Rename completed."

        elif cmd == "clear":
            st.session_state.output = ""
            return True, "Cleared output"

        elif cmd == "help":
            help_text = (
                "Built-in commands: ls, cd, pwd, mkdir, rm, cp, mv, cpu, mem, disk, ps, history, clear, help\n"
                "You can also run shell commands."
            )
            return True, help_text

        elif cmd == "history":
            if not st.session_state.history:
                return True, "No command history"
            history_lines = [f"{i+1}: {cmd}" for i, cmd in enumerate(st.session_state.history[-20:])]
            return True, "\n".join(history_lines)

        else:
            return None, None  # Not an internal command
    except Exception as e:
        return False, f"Error: {e}"

# ---------------------------
# Command execution (streaming)
# ---------------------------
def stream_subprocess(command, cwd, q, shell_mode=False):
    """
    Run a subprocess and stream stdout/stderr lines into a queue.
    """
    # Use Popen with universal_newlines to iterate over lines
    if shell_mode:
        proc = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=cwd, text=True)
    else:
        # command should be list
        proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=cwd, text=True)
    try:
        for line in proc.stdout:
            q.put(line.rstrip("\n"))
        proc.wait()
        q.put(f"--- process exited with code {proc.returncode} ---")
    except Exception as e:
        q.put(f"Error running process: {e}")
    finally:
        q.put(None)  # sentinel

# ---------------------------
# UI Layout
# ---------------------------
st.set_page_config(page_title="Python Web Terminal", layout="wide")
st.title("🖥️ Python Web Command Terminal")
st.markdown(
    """
    **Features:** core file ops (ls, cd, pwd, mkdir, rm, cp, mv), session cwd, command history,
    system monitoring (cpu, mem, disk, processes), real-time output streaming for long-running commands.
    """
)

col1, col2 = st.columns([3, 1])

with col2:
    st.subheader("System Monitor")
    st.write(f"**Current directory:** `{st.session_state.cwd}`")
    st.write("**CPU**")
    st.progress(psutil.cpu_percent(interval=0.1) / 100.0)
    st.write("**Memory**")
    st.progress(psutil.virtual_memory().percent / 100.0)
    st.write("**Disk**")
    st.progress(psutil.disk_usage(st.session_state.cwd).percent / 100.0)
    if st.button("Refresh Monitor"):
        st.rerun()


with col1:
    st.subheader("Terminal")
    cmd_input = st.text_input("Enter command", key="cmd_input", placeholder="e.g. ls -la", autocomplete="off")
    run_button = st.button("Run")
    st.write("### Output")
    output_placeholder = st.empty()
    # show previous output
    if st.session_state.output:
        output_placeholder.text_area("session output", value=st.session_state.output, height=300)

    st.write("### History")
    if st.session_state.history:
        for i, h in enumerate(reversed(st.session_state.history[-20:])):
            st.write(f"{len(st.session_state.history)-i}: {h}")

# ---------------------------
# Handle input / run
# ---------------------------
if run_button and cmd_input.strip():
    cmd = cmd_input.strip()
    st.session_state.history.append(cmd)

    # provide convenient aliases for monitor commands
    if cmd in ("cpu", "mem", "disk", "ps"):
        if cmd == "cpu":
            append_output(f"CPU: {psutil.cpu_percent(interval=0.5)}%")
        elif cmd == "mem":
            vm = psutil.virtual_memory()
            append_output(f"Memory: {vm.percent}% ({vm.used // (1024**2)}MB used of {vm.total // (1024**2)}MB)")
        elif cmd == "disk":
            du = psutil.disk_usage(st.session_state.cwd)
            append_output(f"Disk: {du.percent}% ({du.used // (1024**3)}GB used of {du.total // (1024**3)}GB)")
        elif cmd == "ps":
            procs = []
            for p in psutil.process_iter(['pid', 'name', 'username', 'cpu_percent']):
                procs.append(f"{p.info['pid']:6} {p.info.get('name','')[:25]:25} {p.info.get('username','')[:15]:15} {p.info.get('cpu_percent',0):5}")
            append_output("\n".join(procs))
        # re-render
        st.rerun()


    # parse command for internal handling
    try:
        parts = shlex.split(cmd)
    except Exception:
        parts = cmd.split()

    handled, result = run_internal_command(parts)
    if handled is True:
        append_output(f"$ {cmd}")
        append_output(result)
        st.rerun()

    elif handled is False:
        append_output(f"$ {cmd}")
        append_output(result)
        st.rerun()

    else:
        # Not an internal command -> run via subprocess with streaming
        append_output(f"$ {cmd}")
        st.session_state.running = True

        q = queue.Queue()
        shell_mode = True  # allow shell features like piping by default in the web terminal
        thread = threading.Thread(target=stream_subprocess, args=(cmd, st.session_state.cwd, q, shell_mode), daemon=True)
        thread.start()

        # read queue and update output live
        with st.spinner("Running command..."):
            while True:
                try:
                    line = q.get(timeout=0.1)
                except queue.Empty:
                    st.experimental_rerun() if False else None  # no-op to avoid warnings
                    line = None
                if line is None:
                    # sentinel or no data
                    if not thread.is_alive():
                        break
                    else:
                        time.sleep(0.05)
                        continue
                append_output(line)
                # update UI
                output_placeholder.text_area("session output", value=st.session_state.output, height=300)
            st.session_state.running = False
            st.rerun()


# ---------------------------
# Small helper section
# ---------------------------
st.markdown("---")
st.markdown(
    """
    **Quick Tips**
    - Use `cd <dir>` to change directory. The web terminal keeps a session cwd.
    - File ops run relative to the current directory shown in the System Monitor.
    - For long-running commands (e.g. `ping`, `tail -f`), output will stream as lines arrive.
    - This demo is intended for local use only. Do not expose to the public without auth.
    """
)
