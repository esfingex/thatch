#!/usr/bin/env python3
import sys
import subprocess
import shutil
from pathlib import Path


class ThatchSetup:
    def __init__(self):
        self.current_dir = Path(".").resolve()
        self.venv_dir = self.current_dir / "venv"
        self.bin_dir = Path.home() / ".local" / "bin"
        self.launcher_script = self.bin_dir / "thatch"

    def check_system_dependencies(self):
        """Verifica que winetricks y pacman estén disponibles (Entorno CachyOS/Arch)"""
        print("[*] Verificando dependencias del sistema...")
        if not shutil.which("winetricks"):
            print("[-] Error: 'winetricks' no está instalado en el sistema.")
            print("    Ejecuta: sudo pacman -S winetricks")
            sys.exit(1)
        print("[+] Sistema base verificado.")

    def create_venv(self):
        """Crea el entorno virtual e instala los requerimientos"""
        if self.venv_dir.exists():
            print(f"[!] El entorno virtual ya existe en: {self.venv_dir}")
            return

        print("[*] Creando entorno virtual de Python (venv)...")
        try:
            subprocess.run(
                [sys.executable, "-m", "venv", str(self.venv_dir)], check=True
            )
            print("[+] Entorno virtual creado exitosamente.")
        except subprocess.CalledProcessError as e:
            print(f"[-] Falló la creación del venv: {e}")
            sys.exit(1)

        # Determinar el binario de pip del nuevo venv
        pip_bin = self.venv_dir / "bin" / "pip"

        print("[*] Actualizando pip e instalando PySide6...")
        try:
            subprocess.run([str(pip_bin), "install", "--upgrade", "pip"], check=True)
            subprocess.run([str(pip_bin), "install", "PySide6"], check=True)
            print("[+] Dependencias de Python instaladas correctamente.")
        except subprocess.CalledProcessError as e:
            print(f"[-] Falló la instalación de paquetes con pip: {e}")
            sys.exit(1)

    def create_structure(self):
        """Genera las carpetas necesarias para el funcionamiento de Thatch"""
        print("[*] Generando estructura de directorios...")
        (self.current_dir / "runners").mkdir(exist_ok=True)
        (self.current_dir / "prefixes").mkdir(exist_ok=True)
        print("[+] Directorios /runners y /prefixes listos.")

    def create_global_link(self):
        """Crea el script de ejecución global en ~/.local/bin/thatch"""
        print(f"[*] Configurando acceso directo global en: {self.bin_dir}")
        self.bin_dir.mkdir(parents=True, exist_ok=True)

        python_venv_path = self.venv_dir / "bin" / "python"
        script_path = self.current_dir / "thatch.py"

        # Contenido del wrapper de ejecución limpia
        launcher_content = f"""#!/usr/bin/env bash
# Script generado automáticamente por Thatch Setup
{python_venv_path} {script_path} "$@"
"""

        try:
            with open(self.launcher_script, "w") as f:
                f.write(launcher_content)

            # Dar permisos de ejecución (chmod +x)
            self.launcher_script.chmod(self.launcher_script.stat().st_mode | 0o111)
            print("[+] Comando 'thatch' creado con éxito.")
        except Exception as e:
            print(f"[-] No se pudo escribir el script lanzador: {e}")

    def run(self):
        print("=== Iniciando Configuración de Thatch ===")
        self.check_system_dependencies()
        self.create_structure()
        self.create_venv()

        print("\n[?] ¿Deseas crear un enlace global en tu sistema?")
        print(
            "    (Esto creará un comando 'thatch' en ~/.local/bin para ejecutarlo desde cualquier terminal)"
        )
        try:
            resp = input("    Instalar globalmente [S/n]: ").strip().lower()
        except EOFError:
            resp = "s"

        if resp in ("", "s", "si", "y", "yes"):
            self.create_global_link()
            print("\n[+] Instalación completada.")
            print("[!] Nota: Asegúrate de que '~/.local/bin' esté en tu $PATH.")
            print("[*] Ya puedes ejecutar 'thatch' desde cualquier terminal.")
        else:
            print("\n[+] Configuración local completada.")
            print("[*] Puedes ejecutar la app usando tu entorno virtual local:")
            print("    source venv/bin/activate")
            print("    python thatch.py")


if __name__ == "__main__":
    setup = ThatchSetup()
    setup.run()
