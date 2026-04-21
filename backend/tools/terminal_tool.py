"""Stub for tools.terminal_tool."""

def run_terminal_command(cmd: str, cwd: str = None, env: dict = None):
    import subprocess
    result = subprocess.run(cmd, shell=True, cwd=cwd, env=env, capture_output=True)
    return result.stdout.decode(), result.stderr.decode(), result.returncode