"""Create a source ZIP excluding secrets, workspaces, and interpreter caches."""
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parent
TOP_LEVEL = {
    "app.py", "build_submission.py", "README.md", "requirements.txt", "Dockerfile",
    ".dockerignore", ".gitignore", ".env.example", "render.yaml",
}
SOURCE_FOLDERS = {"studydesk", "tests", "docs"}


def main():
    output = ROOT / "submission"
    output.mkdir(exist_ok=True)
    archive = output / "studydesk-assignment4.zip"
    files = []
    for path in ROOT.rglob("*"):
        relative = path.relative_to(ROOT)
        if not path.is_file() or "__pycache__" in relative.parts or path.suffix in (".pyc", ".pyo"):
            continue
        if relative.as_posix() in TOP_LEVEL or relative.parts[0] in SOURCE_FOLDERS:
            files.append(path)
    with ZipFile(archive, "w", ZIP_DEFLATED) as bundle:
        for path in sorted(files):
            bundle.write(path, path.relative_to(ROOT).as_posix())
    with ZipFile(archive) as bundle:
        if bundle.testzip() is not None:
            raise RuntimeError("ZIP integrity check failed")
    print(f"Created {archive} ({len(files)} files)")


if __name__ == "__main__":
    main()
