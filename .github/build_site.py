"""Build the Kodi repository website into _site/ (published to GitHub Pages).

Layout Kodi expects (see repository.moodycam/addon.xml):
  addons.xml, addons.xml.md5               index of add-ons and versions
  <addon id>/<addon id>-<version>.zip      the add-on zips
  repository.moodycam-<version>.zip        copy at the top, for "Install from zip"
  index.html (in every folder)             links to every file, for Kodi's browser

Run from anywhere: python .github/build_site.py
"""
import hashlib
import os
import re
import shutil
import subprocess
import zipfile
from xml.etree import ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "_site")
SERVICE_ID = "service.moodycam"
REPO_ID = "repository.moodycam"


def version_of(addon_xml):
    return ET.parse(addon_xml).getroot().get("version")


def addon_entry(addon_xml):
    """The addon.xml text without its <?xml ...?> line, for addons.xml."""
    with open(addon_xml, encoding="utf-8") as f:
        text = f.read()
    return re.sub(r"^\s*<\?xml[^>]*\?>\s*", "", text).strip()


def build_service():
    version = version_of(os.path.join(ROOT, "addon.xml"))
    folder = os.path.join(OUT, SERVICE_ID)
    os.makedirs(folder)
    path = os.path.join(folder, "%s-%s.zip" % (SERVICE_ID, version))
    # git archive packs committed files only; .gitattributes leaves out
    # repo-only files (README, .github, the repository add-on, ...).
    subprocess.check_call(["git", "archive", "--format=zip",
                           "--prefix=%s/" % SERVICE_ID, "-o", path, "HEAD"], cwd=ROOT)
    return path


def build_repository():
    src = os.path.join(ROOT, REPO_ID)
    version = version_of(os.path.join(src, "addon.xml"))
    folder = os.path.join(OUT, REPO_ID)
    os.makedirs(folder)
    name = "%s-%s.zip" % (REPO_ID, version)
    path = os.path.join(folder, name)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(os.path.join(src, "addon.xml"), "%s/addon.xml" % REPO_ID)
        z.write(os.path.join(ROOT, "resources", "media", "icon.png"), "%s/icon.png" % REPO_ID)
    shutil.copy(path, os.path.join(OUT, name))
    return name


def build_index(repo_zip_name):
    entries = [addon_entry(os.path.join(ROOT, "addon.xml")),
               addon_entry(os.path.join(ROOT, REPO_ID, "addon.xml"))]
    xml = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<addons>\n'
           + "\n".join(entries) + "\n</addons>\n")
    with open(os.path.join(OUT, "addons.xml"), "w", encoding="utf-8", newline="\n") as f:
        f.write(xml)
    with open(os.path.join(OUT, "addons.xml.md5"), "w", newline="\n") as f:
        f.write(hashlib.md5(xml.encode("utf-8")).hexdigest())


def write_listings():
    """Write an index.html in every folder that links to everything in it.

    Kodi caches the file list of any web folder it has browsed (for example
    when the user adds the source in the File manager). If a file isn't in
    that list, Kodi treats it as missing without even asking the server, so
    the repository's addons.xml.md5 lookup fails. Listing every file avoids
    that.
    """
    for base, dirs, files in os.walk(OUT):
        entries = sorted(d + "/" for d in dirs) + sorted(f for f in files if f != "index.html")
        links = "\n".join('<a href="%s">%s</a><br>' % (e, e) for e in entries)
        with open(os.path.join(base, "index.html"), "w", encoding="utf-8", newline="\n") as f:
            f.write('<!DOCTYPE html>\n<html><head><meta charset="utf-8"><title>MoodyCam</title></head>\n'
                    "<body>\n%s\n</body></html>\n" % links)


def main():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)
    service_zip = build_service()
    repo_zip_name = build_repository()
    build_index(repo_zip_name)
    write_listings()
    print("built %s" % OUT)
    for base, _, files in os.walk(OUT):
        for name in sorted(files):
            print("  " + os.path.relpath(os.path.join(base, name), OUT).replace(os.sep, "/"))
    return service_zip


if __name__ == "__main__":
    main()
