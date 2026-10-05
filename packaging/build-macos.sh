#!/bin/bash
# Build the macOS .app + release zip.
#
#   bash packaging/build-macos.sh
#
# Needs macOS, python3.12 (with tkinter) and network access for PyInstaller.
# Produces:
#   dist/ObraDinnInstructor.app
#   dist/ObraDinnInstructor-1.0.0-macos-x86_64.zip
set -e

VER=1.0.0
NAME="ObraDinnInstructor-${VER}-macos-x86_64"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PY="${PYTHON:-/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12}"

echo "--- 1. png -> icns"
rm -rf /tmp/icon.iconset icon-instructor.icns
mkdir -p /tmp/icon.iconset
for s in 16 32 64 128 256 512; do
  sips -z $s $s icon-instructor.png --out /tmp/icon.iconset/icon_${s}x${s}.png >/dev/null
  sips -z $((s*2)) $((s*2)) icon-instructor.png --out /tmp/icon.iconset/icon_${s}x${s}@2x.png >/dev/null
done
iconutil -c icns /tmp/icon.iconset -o icon-instructor.icns

echo "--- 2. venv + pyinstaller"
if [ ! -x .venv/bin/python ]; then "$PY" -m venv .venv; fi
.venv/bin/python -m pip install -q --upgrade pip
.venv/bin/python -m pip install -q pyinstaller
echo -n "pyinstaller "; .venv/bin/python -m PyInstaller --version

echo "--- 3. build .app"
rm -rf build dist
.venv/bin/python -m PyInstaller --noconfirm ObraDinnInstructor.spec 2>&1 | tail -4
APP=dist/ObraDinnInstructor.app
ls -d "$APP"

# langtool is shipped as *data*, so PyInstaller does not give it the exec bit.
# Without +x the hook silently degrades to "old langtool"; and since we just
# modified the bundle, re-sign it ad-hoc afterwards.
echo "--- 3b. langtool in bundle"
LT="$APP/Contents/Frameworks/instructor/langtool"
if [ -f "$LT" ]; then
  chmod +x "$LT"
  ls -l "$LT" | awk '{print $1, $5, $9}'
  codesign --force --deep --sign - "$APP" >/dev/null 2>&1 && echo "re-signed ad-hoc"
else
  echo "!! no langtool in bundle (run: dotnet publish ... -r osx-x64 first)"
fi

echo "--- 4. smoke"
"$APP/Contents/MacOS/ObraDinnInstructor" check 2>&1 | tail -4
"$APP/Contents/MacOS/ObraDinnInstructor" hook --report 2>&1 | tail -4

echo "--- 5. release zip"
pkill -f "ObraDinnInstructor.app/Contents/MacOS" 2>/dev/null || true
sleep 1
rm -rf "dist/$NAME" "dist/$NAME.zip"
mkdir -p "dist/$NAME"
cp -R "$APP" "dist/$NAME/"
rm -f "dist/$NAME/ObraDinnInstructor.app/Contents/Frameworks/instructor/fonts/_charset.txt" 2>/dev/null || true
( cd dist && ditto -c -k --sequesterRsrc --keepParent "$NAME" "$NAME.zip" )

echo "--- result"
ls -lh "dist/$NAME.zip" | awk '{print $5, $9}'
shasum -a 256 "dist/$NAME.zip" | awk '{print $1}'
