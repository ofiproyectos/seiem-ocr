from __future__ import annotations

import argparse
from getpass import getpass
from hashlib import pbkdf2_hmac
from secrets import token_hex


def hash_password(password: str) -> str:
    iterations = 260_000
    salt = token_hex(16)
    hashed = pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations).hex()
    return f"pbkdf2_sha256${iterations}${salt}${hashed}"


def sql_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "''")


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera SQL para crear un usuario de revision.")
    parser.add_argument("username", help="Usuario de acceso")
    parser.add_argument("nombre", help="Nombre visible")
    parser.add_argument("--password", help="Contrasena. Si se omite, se solicita de forma oculta.")
    args = parser.parse_args()

    password = args.password or getpass("Contrasena: ")
    password_hash = hash_password(password)
    print(
        "INSERT INTO usuarios_revision (username, nombre, password_hash, rol, activo) "
        f"VALUES ('{sql_escape(args.username)}', '{sql_escape(args.nombre)}', '{password_hash}', 'revision', 1);"
    )


if __name__ == "__main__":
    main()
