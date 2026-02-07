# Script Manager for QGIS

**DE** | [EN](#english)

---

## Deutsch

Ein QGIS-Plugin zur Verwaltung, Ausf&uuml;hrung und Fehlersuche von PyQGIS-Scripten. Mit visuellem Script-Browser, integrierter Konsole, anpassbarer Toolbar und sicherer Ausf&uuml;hrungsumgebung.

> Fork von [TiagoJoseMS/script-manager](https://github.com/TiagoJoseMS/script-manager) &mdash; umfassend &uuml;berarbeitet und erweitert.

### Funktionen

| Funktion | Beschreibung |
|----------|-------------|
| **Script-Browser** | Dialog mit Scriptliste, Beschreibung, Pfadanzeige und integrierter Konsole |
| **Toolbar** | Anpassbare Toolbar &mdash; Lieblingsscripte per Klick starten |
| **Schnellzugriff** | Men&uuml;system f&uuml;r direkte Script-Ausf&uuml;hrung |
| **Datei&uuml;berwachung** | Automatisches Erkennen und Nachladen ge&auml;nderter Scripte |
| **Sichere Ausf&uuml;hrung** | Validierung vor Ausf&uuml;hrung, Crash-Schutz, Fehlerbehandlung |
| **Konsolen-Capture** | `print()`-Ausgaben und Fehler in Echtzeit im Browser |
| **Qt5/Qt6** | Volle Kompatibilit&auml;t mit beiden Qt-Versionen |
| **Mehrsprachig** | EN, PT-BR (erweiterbar) |

### Installation

**&Uuml;ber QGIS Plugin-Manager:**
1. QGIS &ouml;ffnen &rarr; **Erweiterungen** &rarr; **Erweiterungen verwalten und installieren**
2. Nach "Script Manager" suchen &rarr; **Installieren**

**Manuell:**
1. Repository herunterladen/klonen
2. In das QGIS-Plugin-Verzeichnis kopieren:
   - **Windows:** `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\script-manager`
   - **macOS:** `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/script-manager`
   - **Linux:** `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/script-manager`
3. QGIS neu starten und Plugin aktivieren

### Script-Format (Docstring)

Scripte werden &uuml;ber Metadaten im Docstring gesteuert:

```python
# -*- coding: utf-8 -*-
"""
Mein Analyse-Tool
Description: F&uuml;hrt eine Layer-Analyse durch
Toolbar: true
ToolbarLabel: Analyse
Validated: true
"""
from qgis.core import QgsProject

def main():
    layers = QgsProject.instance().mapLayers()
    print(f"Projekt hat {len(layers)} Layer")

if __name__ == "__main__":
    main()
```

| Feld | Wirkung |
|------|---------|
| `Description:` | Beschreibung im Browser und Tooltip (auch `Descri&ccedil;&atilde;o:`) |
| `Toolbar: true` | Script erscheint als Button in der Toolbar |
| `ToolbarLabel:` | Benutzerdefinierter kurzer Name f&uuml;r den Toolbar-Button |
| `Validated: true` | Sicherheitswarnung wird nach einmaliger Best&auml;tigung pro Sitzung unterdr&uuml;ckt |

### Benutzung

1. **Script Manager** &rarr; **Script Browser** &ouml;ffnen
2. Script in der Liste ausw&auml;hlen
3. Beschreibung und Pfad werden angezeigt
4. **Execute Script** startet das Script, Ausgabe erscheint im Output-Tab
5. &Uuml;ber die **Toolbar** k&ouml;nnen Favoriten-Scripte direkt gestartet werden

### Sicherheit

Das Plugin validiert Scripte vor der Ausf&uuml;hrung und warnt bei:
- `subprocess.call`, `subprocess.run`, `subprocess.Popen`
- `os.system()`, `eval()`, `exec()`, `__import__()`

Scripte mit `Validated: true` im Docstring werden nach einmaliger Best&auml;tigung pro Sitzung ohne erneute Warnung ausgef&uuml;hrt.

### Systemvoraussetzungen

- QGIS 3.0+
- Python 3.6+
- Qt5 oder Qt6
- Windows, macOS, Linux

---

<a name="english"></a>

## English

A QGIS plugin for managing, executing, and debugging PyQGIS scripts. Features a visual script browser, integrated console, customizable toolbar, and safe execution environment.

> Fork of [TiagoJoseMS/script-manager](https://github.com/TiagoJoseMS/script-manager) &mdash; extensively reworked and extended.

### Features

| Feature | Description |
|---------|-------------|
| **Script Browser** | Dialog with script list, description, path display, and integrated console |
| **Toolbar** | Customizable toolbar &mdash; launch favorite scripts with one click |
| **Quick Access** | Menu system for direct script execution |
| **File Monitoring** | Automatic detection and reloading of changed scripts |
| **Safe Execution** | Pre-execution validation, crash protection, error handling |
| **Console Capture** | `print()` output and errors displayed in real-time in the browser |
| **Qt5/Qt6** | Full compatibility with both Qt versions |
| **Multi-language** | EN, PT-BR (extensible) |

### Installation

**Via QGIS Plugin Manager:**
1. Open QGIS &rarr; **Plugins** &rarr; **Manage and Install Plugins**
2. Search for "Script Manager" &rarr; **Install**

**Manual:**
1. Download/clone repository
2. Copy to the QGIS plugin directory:
   - **Windows:** `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\script-manager`
   - **macOS:** `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/script-manager`
   - **Linux:** `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/script-manager`
3. Restart QGIS and enable the plugin

### Script Format (Docstring)

Scripts are controlled via metadata in the docstring:

```python
# -*- coding: utf-8 -*-
"""
My Analysis Tool
Description: Performs a layer analysis
Toolbar: true
ToolbarLabel: Analyze
Validated: true
"""
from qgis.core import QgsProject

def main():
    layers = QgsProject.instance().mapLayers()
    print(f"Project has {len(layers)} layers")

if __name__ == "__main__":
    main()
```

| Field | Effect |
|-------|--------|
| `Description:` | Description shown in browser and tooltip (also `Descri&ccedil;&atilde;o:`) |
| `Toolbar: true` | Script appears as a button in the toolbar |
| `ToolbarLabel:` | Custom short name for the toolbar button |
| `Validated: true` | Security warning suppressed after one-time acknowledgment per session |

### Usage

1. Open **Script Manager** &rarr; **Script Browser**
2. Select a script from the list
3. Description and path are displayed
4. **Execute Script** runs the script, output appears in the Output tab
5. Use the **Toolbar** to launch favorite scripts directly

### Security

The plugin validates scripts before execution and warns about:
- `subprocess.call`, `subprocess.run`, `subprocess.Popen`
- `os.system()`, `eval()`, `exec()`, `__import__()`

Scripts with `Validated: true` in the docstring are executed without repeated warnings after a one-time acknowledgment per session.

### System Requirements

- QGIS 3.0+
- Python 3.6+
- Qt5 or Qt6
- Windows, macOS, Linux

---

## Changelog

### Version 2.0 (Fork)
- Customizable toolbar with favorite script buttons (`Toolbar: true`)
- Custom toolbar button labels (`ToolbarLabel:`)
- Warning suppression for validated scripts (`Validated: true`)
- Professional script browser redesign
- Professional about dialog redesign
- Regex-based script validation (fewer false positives)
- Status bar messages (non-intrusive)
- Data-driven Qt5/Qt6 compatibility layer
- Comprehensive code refactoring (-30% LOC)
- Bilingual README (DE/EN)

### Version 1.0 (Original)
- Script browser with detailed information
- Quick access menu system
- Automatic file system monitoring
- Multi-language support (EN, PT-BR)
- Qt5/Qt6 compatibility
- Safe script execution environment
- Console output capture

## Credits

**Author:** Thomas W&ouml;lk

**Original Plugin:** [Tiago Jos&eacute; M. Silva](https://github.com/TiagoJoseMS/script-manager)

## License

GNU General Public License v2.0 &mdash; see [LICENSE](LICENSE).
