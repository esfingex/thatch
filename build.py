#!/usr/bin/env python3
import sys
import subprocess
import shutil
from pathlib import Path


class ThatchCompiler:
    def __init__(self):
        self.base_dir = Path(".").resolve()
        self.venv_bin = self.base_dir / "venv" / "bin"
        self.pyinstaller_bin = self.venv_bin / "pyinstaller"
        self.script_to_compile = (
            self.base_dir / "thatch.py"
        )  # Cambia a thatch.py si renombraste el archivo

    def install_compiler_deps(self):
        """Asegura que PyInstaller esté en el entorno virtual"""
        pip_bin = self.venv_bin / "pip"
        if not pip_bin.exists():
            print(
                "[-] Error: No se encontró el entorno virtual 'venv'. Ejecuta primero tu instalador."
            )
            sys.exit(1)

        print("[*] Instalando instalador de binarios (PyInstaller) en el venv...")
        try:
            subprocess.run([str(pip_bin), "install", "pyinstaller"], check=True)
        except subprocess.CalledProcessError:
            print("[-] Error instalando dependencias de compilación.")
            sys.exit(1)

    def compile_binary(self):
        """Compila el script a un único ejecutable nativo de Linux"""
        if not self.script_to_compile.exists():
            print(
                f"[-] Error: No se encuentra el archivo de código fuente: {self.script_to_compile}"
            )
            sys.exit(1)

        print(f"[*] Compilando {self.script_to_compile.name} a binario nativo...")

        # Parámetros de PyInstaller:
        # --onefile: Empaqueta todo en un único binario ejecutable
        # --clean: Limpia la caché antes de construir
        # --name: Nombra al binario final como 'thatch'
        cmd = [
            str(self.pyinstaller_bin),
            "--onefile",
            "--clean",
            "--name",
            "thatch",
            str(self.script_to_compile),
        ]

        try:
            subprocess.run(cmd, check=True)
            print("[+] Compilación exitosa.")
        except subprocess.CalledProcessError:
            print("[-] Error durante la compilación del binario.")
            sys.exit(1)

    def deploy_binary(self):
        """Mueve el ejecutable final a ~/.local/bin para acceso global"""
        dist_binary = self.base_dir / "dist" / "thatch"
        target_dir = Path.home() / ".local" / "bin"
        target_binary = target_dir / "thatch"

        if dist_binary.exists():
            target_dir.mkdir(parents=True, exist_ok=True)
            print(f"[*] Desplegando ejecutable en: {target_binary}")
            shutil.copy2(dist_binary, target_binary)

            # Limpieza de temporales de compilación para dejar el repo limpio
            print("[*] Limpiando residuos de compilación...")
            shutil.rmtree(self.base_dir / "build", ignore_errors=True)
            shutil.rmtree(self.base_dir / "dist", ignore_errors=True)
            spec_file = self.base_dir / "thatch.spec"
            if spec_file.exists():
                spec_file.unlink()

            print(
                "[+] ¡Listo! El binario nativo 'thatch' está operativo y el entorno limpio."
            )
        else:
            print("[-] Error: No se encontró el binario generado en la carpeta 'dist'.")

    def run(self):
        self.install_compiler_deps()
        self.compile_binary()
        self.deploy_binary()


if __name__ == "__main__":
    compiler = ThatchCompiler()
    compiler.run()
