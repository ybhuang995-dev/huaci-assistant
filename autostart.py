"""
开机自启模块
-----------
通过 Windows 注册表 Run 键控制是否在系统启动时自动运行划词助手。
打包前注册 pythonw.exe + main.py 路径，打包后直接注册 .exe 路径。
"""

import sys
import winreg
from pathlib import Path

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_APP_NAME = "划词助手"


def _get_command() -> str:
    """返回启动命令 —— 打包后是 exe 路径，开发时是 pythonw + main.py"""
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后：直接运行 exe
        return f'"{sys.executable}"'
    else:
        # 开发环境：pythonw.exe 运行 main.py
        main_py = Path(__file__).parent / "main.py"
        # pythonw.exe 和 python.exe 同目录，不带控制台窗口
        exe_dir = Path(sys.executable).parent
        pythonw = exe_dir / "pythonw.exe"
        if not pythonw.exists():
            # 备选：直接搜 PATH
            pythonw = "pythonw.exe"
        return f'"{pythonw}" "{main_py}"'


def is_enabled() -> bool:
    """检查开机自启是否已开启"""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY,
                             0, winreg.KEY_READ)
        try:
            winreg.QueryValueEx(key, _APP_NAME)
            return True
        except FileNotFoundError:
            return False
        finally:
            winreg.CloseKey(key)
    except OSError:
        return False


def set_enabled(enable: bool) -> None:
    """设置开机自启开关"""
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY,
                         0, winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE)
    if enable:
        cmd = _get_command()
        winreg.SetValueEx(key, _APP_NAME, 0, winreg.REG_SZ, cmd)
    else:
        try:
            winreg.DeleteValue(key, _APP_NAME)
        except FileNotFoundError:
            pass
    winreg.CloseKey(key)
