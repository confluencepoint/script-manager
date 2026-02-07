# -*- coding: utf-8 -*-
"""
Script Manager Plugin for QGIS
Monitors and executes PyQGIS scripts automatically with enhanced error handling
Compatible with both Qt5 and Qt6
Author: Tiago José M Silva
"""

import os
import sys
import re
import traceback
import io
import contextlib

from qgis.PyQt.QtCore import QTimer, QFileSystemWatcher, pyqtSignal, QObject, QSettings, QT_VERSION_STR
from qgis.PyQt.QtWidgets import (QApplication, QAction, QMenu, QMessageBox, QDialog, QVBoxLayout,
                                QHBoxLayout, QListWidget, QListWidgetItem, QLabel,
                                QPushButton, QTextEdit, QSplitter, QWidget, QScrollArea,
                                QTabWidget, QPlainTextEdit, QToolButton)
from qgis.PyQt.QtGui import QIcon, QFont, QTextCursor
from qgis.PyQt.QtCore import Qt

QT_VERSION = 6 if QT_VERSION_STR.startswith('6') else 5

from qgis.core import QgsMessageLog, Qgis
from qgis.utils import iface


class SafeScriptExecutor:
    """Script executor with output capture and error handling"""
    
    def __init__(self):
        self.output_buffer = io.StringIO()
        self.error_buffer = io.StringIO()
    
    @contextlib.contextmanager
    def capture_output(self):
        """Context manager to capture stdout and stderr"""
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        try:
            sys.stdout = self.output_buffer
            sys.stderr = self.error_buffer
            yield
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
    
    def get_captured_output(self):
        """Get captured output and errors"""
        output = self.output_buffer.getvalue()
        errors = self.error_buffer.getvalue()
        
        self.output_buffer.truncate(0)
        self.output_buffer.seek(0)
        self.error_buffer.truncate(0)
        self.error_buffer.seek(0)
        
        return output, errors
    
    RISKY_PATTERNS = [
        (r'\bsubprocess\s*\.\s*call\b', 'subprocess.call'),
        (r'\bsubprocess\s*\.\s*run\b', 'subprocess.run'),
        (r'\bsubprocess\s*\.\s*Popen\b', 'subprocess.Popen'),
        (r'\bos\s*\.\s*system\s*\(', 'os.system()'),
        (r'(?<!\w)eval\s*\(', 'eval()'),
        (r'(?<!\w)exec\s*\(', 'exec()'),
        (r'\b__import__\s*\(', '__import__()'),
    ]

    def validate_script_imports(self, script_content):
        """Check for risky patterns in non-comment lines."""
        code = '\n'.join(l for l in script_content.split('\n') if not l.lstrip().startswith('#'))
        return [f"⚠️ Potentially risky operation detected: {label}"
                for pattern, label in self.RISKY_PATTERNS if re.search(pattern, code)]
    
    def prepare_safe_namespace(self, script_path):
        """Prepare a safe execution namespace with common QGIS/Qt/stdlib imports."""
        import json, math, datetime
        from qgis.core import (
            QgsProject, QgsVectorLayer, QgsRasterLayer, QgsMessageLog, Qgis,
            QgsUnitTypes, QgsWkbTypes, QgsFeature, QgsGeometry,
            QgsCoordinateReferenceSystem, QgsCoordinateTransform,
            QgsMapLayerProxyModel, QgsProcessingContext
        )
        from qgis.gui import QgsMapCanvas, QgsMapTool
        from qgis.utils import iface as qgis_iface
        from qgis.PyQt.QtWidgets import (QMessageBox, QInputDialog, QFileDialog,
                                         QProgressBar, QComboBox, QCheckBox)
        from qgis.PyQt.QtCore import Qt, QTimer, QThread, pyqtSignal
        from qgis.PyQt.QtGui import QIcon, QPixmap, QColor

        return {
            '__name__': '__main__', '__file__': script_path, 'QT_VERSION': QT_VERSION,
            'QgsProject': QgsProject, 'QgsVectorLayer': QgsVectorLayer,
            'QgsRasterLayer': QgsRasterLayer, 'QgsFeature': QgsFeature,
            'QgsGeometry': QgsGeometry, 'QgsMessageLog': QgsMessageLog, 'Qgis': Qgis,
            'QgsCoordinateReferenceSystem': QgsCoordinateReferenceSystem,
            'QgsCoordinateTransform': QgsCoordinateTransform,
            'QgsUnitTypes': QgsUnitTypes, 'QgsWkbTypes': QgsWkbTypes,
            'QgsMapCanvas': QgsMapCanvas, 'QgsMapTool': QgsMapTool,
            'QgsMapLayerProxyModel': QgsMapLayerProxyModel,
            'QgsProcessingContext': QgsProcessingContext,
            'iface': qgis_iface,
            'QMessageBox': QMessageBox, 'QInputDialog': QInputDialog,
            'QFileDialog': QFileDialog, 'QProgressBar': QProgressBar,
            'QComboBox': QComboBox, 'QCheckBox': QCheckBox,
            'Qt': Qt, 'QTimer': QTimer, 'QThread': QThread, 'pyqtSignal': pyqtSignal,
            'QIcon': QIcon, 'QPixmap': QPixmap, 'QColor': QColor,
            'json': json, 'math': math, 'datetime': datetime, 're': re,
        }


class QtCompat:
    """Qt compatibility helper — resolves Qt5/Qt6 enum differences via lookup."""

    _ENUMS = {
        'user_role':        (Qt, 'ItemDataRole.UserRole', 'UserRole'),
        'horizontal':       (Qt, 'Orientation.Horizontal', 'Horizontal'),
        'rich_text':        (Qt, 'TextFormat.RichText', 'RichText'),
        'pointing_hand':    (Qt, 'CursorShape.PointingHandCursor', 'PointingHandCursor'),
        'text_beside_icon': (Qt, 'ToolButtonStyle.ToolButtonTextBesideIcon', 'ToolButtonTextBesideIcon'),
        'font_bold':        (QFont, 'Weight.Bold', 'Bold'),
    }

    @staticmethod
    def get(name):
        obj, qt6_path, qt5_attr = QtCompat._ENUMS[name]
        if QT_VERSION == 6:
            # Resolve dotted path: e.g. Qt -> ItemDataRole -> UserRole
            result = obj
            for part in qt6_path.split('.'):
                result = getattr(result, part)
            return result
        return getattr(obj, qt5_attr)

    @staticmethod
    def exec_dialog(dialog):
        return dialog.exec() if QT_VERSION == 6 else dialog.exec_()


class Translator:
    """Translation manager for the Script Manager plugin"""
    
    def __init__(self):
        self.current_language = self.detect_qgis_language()
        self.translations = self.load_translations()
    
    def detect_qgis_language(self):
        try:
            settings = QSettings()
            locale = settings.value('locale/userLocale', 'en_US')
            language = locale[:2].lower()
            
            language_map = {
                'pt': 'pt_BR',
                'es': 'es_ES',
                'fr': 'fr_FR',
                'de': 'de_DE',
                'it': 'it_IT',
            }
            
            return language_map.get(language, language)
            
        except Exception:
            return 'en'
    
    def load_translations(self):
        return {
            'en': {
                'script_manager': 'Script Manager',
                'script_browser': 'Script Browser',
                'quick_access': 'Quick Access',
                'reload_scripts': 'Reload Scripts',
                'open_scripts_folder': 'Open Scripts Folder',
                'about': 'About',
                'no_scripts_found': 'No scripts found',
                'available_scripts': 'Available Scripts',
                'scripts_found': 'scripts found',
                'scripts': 'Scripts:',
                'select_script': 'Select a script',
                'description': 'Description:',
                'location': 'Location:',
                'file': 'File:',
                'execute_script': 'Execute Script',
                'refresh_list': 'Refresh List',
                'open_folder': 'Open Folder',
                'close': 'Close',
                'no_script_selected': 'No script selected',
                'output': 'Output',
                'console_output': 'Console Output',
                'clear_output': 'Clear Output',
                'warnings': 'Warnings',
                'script_executed': 'Script executed successfully!',
                'script_executed_warnings': 'Script executed with warnings',
                'error_executing': 'Error executing script',
                'scripts_reloaded': 'Scripts reloaded',
                'browser_opened': 'Browser opened with',
                'no_scripts_warning': 'No scripts found in folder',
                'error_opening_folder': 'Error opening folder',
                'output_captured': 'Output captured from script',
                'about_title': 'Script Manager v2.0',
                'about_subtitle': 'PyQGIS Script Management Plugin',
                'about_description': 'A robust environment for managing, executing, and debugging PyQGIS scripts within QGIS.',
                'about_features': 'Features',
                'about_feature_1': 'Script Browser with integrated console and output capture',
                'about_feature_2': 'Customizable toolbar with favorite script buttons',
                'about_feature_3': 'Safe execution with pre-validation and error handling',
                'about_feature_4': 'Automatic file monitoring and instant reloading',
                'about_feature_5': 'Full Qt5/Qt6 compatibility',
                'about_scripts_loaded': 'Scripts loaded',
                'about_scripts_folder': 'Scripts folder',
                'about_docstring_ref': 'Docstring Reference',
                'about_author': 'Author',
                'about_original': 'Based on',
                'error': 'Error',
                'script_error': 'Script Error',
                'validation_warnings': 'Script Validation Warnings',
                'check_log': 'Check QGIS log for more details.',
                'tooltip_browser': 'Open browser with detailed script descriptions and output capture',
                'tooltip_reload': 'Reload all scripts from folder',
                'tooltip_folder': 'Open the folder where scripts are stored',
                'tooltip_about': 'Information about Script Manager',
                'toolbar_script_manager': 'Script Manager',
                'toolbar_reload': 'R',
                'toolbar_open_folder': 'F',
            },
            
            'pt_BR': {
                'script_manager': 'Gerenciador de Scripts',
                'script_browser': 'Navegador de Scripts',
                'quick_access': 'Acesso Rápido',
                'reload_scripts': 'Recarregar Scripts',
                'open_scripts_folder': 'Abrir Pasta de Scripts',
                'about': 'Sobre',
                'no_scripts_found': 'Nenhum script encontrado',
                'available_scripts': 'Scripts Disponíveis',
                'scripts_found': 'scripts encontrados',
                'scripts': 'Scripts:',
                'select_script': 'Selecione um script',
                'description': 'Descrição:',
                'location': 'Localização:',
                'file': 'Arquivo:',
                'execute_script': 'Executar Script',
                'refresh_list': 'Atualizar Lista',
                'open_folder': 'Abrir Pasta',
                'close': 'Fechar',
                'no_script_selected': 'Nenhum script selecionado',
                'output': 'Saída',
                'console_output': 'Saída do Console',
                'clear_output': 'Limpar Saída',
                'warnings': 'Avisos',
                'script_executed': 'Script executado com sucesso!',
                'script_executed_warnings': 'Script executado com avisos',
                'error_executing': 'Erro ao executar script',
                'scripts_reloaded': 'Scripts recarregados',
                'browser_opened': 'Navegador aberto com',
                'no_scripts_warning': 'Nenhum script encontrado na pasta',
                'error_opening_folder': 'Erro ao abrir pasta',
                'output_captured': 'Saída capturada do script',
                'about_title': 'Gerenciador de Scripts v2.0',
                'about_subtitle': 'Plugin de Gerenciamento de Scripts PyQGIS',
                'about_description': 'Um ambiente robusto para gerenciar, executar e depurar scripts PyQGIS dentro do QGIS.',
                'about_features': 'Recursos',
                'about_feature_1': 'Navegador de Scripts com console integrado e captura de saída',
                'about_feature_2': 'Barra de ferramentas personalizável com botões de scripts favoritos',
                'about_feature_3': 'Execução segura com pré-validação e tratamento de erros',
                'about_feature_4': 'Monitoramento automático de arquivos e recarregamento instantâneo',
                'about_feature_5': 'Compatibilidade completa com Qt5/Qt6',
                'about_scripts_loaded': 'Scripts carregados',
                'about_scripts_folder': 'Pasta de scripts',
                'about_docstring_ref': 'Referência do Docstring',
                'about_author': 'Autor',
                'about_original': 'Baseado em',
                'error': 'Erro',
                'script_error': 'Erro no Script',
                'validation_warnings': 'Avisos de Validação do Script',
                'check_log': 'Verifique o log do QGIS para mais detalhes.',
                'tooltip_browser': 'Abrir navegador com descrições detalhadas dos scripts e captura de saída',
                'tooltip_reload': 'Recarregar todos os scripts da pasta',
                'tooltip_folder': 'Abrir a pasta onde os scripts são armazenados',
                'tooltip_about': 'Informações sobre o Gerenciador de Scripts',
                'toolbar_script_manager': 'Gerenciador de Scripts',
                'toolbar_reload': 'R',
                'toolbar_open_folder': 'F',
            }
        }
    
    def tr(self, key, fallback=None):
        if fallback is None:
            fallback = key
        
        if self.current_language in self.translations:
            return self.translations[self.current_language].get(key, fallback)
        
        if 'en' in self.translations:
            return self.translations['en'].get(key, fallback)
        
        return fallback


_translator = Translator()

def tr(key, fallback=None):
    return _translator.tr(key, fallback)


class ScriptWatcher(QObject):
    """File system watcher for monitoring changes in the scripts folder"""
    
    scripts_changed = pyqtSignal()
    
    def __init__(self, scripts_path):
        super().__init__()
        self.scripts_path = scripts_path
        self.watcher = QFileSystemWatcher()
        self.watcher.directoryChanged.connect(self.on_directory_changed)
        self.watcher.fileChanged.connect(self.on_file_changed)
        
        if os.path.exists(scripts_path):
            self.watcher.addPath(scripts_path)
    
    def on_directory_changed(self, path):
        self.scripts_changed.emit()
    
    def on_file_changed(self, path):
        if os.path.exists(path) and path not in self.watcher.files():
            self.watcher.addPath(path)
        self.scripts_changed.emit()
    
    def add_file_to_watch(self, file_path):
        if os.path.exists(file_path) and file_path not in self.watcher.files():
            self.watcher.addPath(file_path)


class ScriptBrowserDialog(QDialog):
    """Professional script browser with output capture and error handling."""

    # Centralized stylesheets
    _CSS = {
        'description': """QTextEdit {
            background-color: #f8f9fa; border: 1px solid #dee2e6;
            border-radius: 4px; padding: 8px; font-size: 11px; }""",
        'console': """QPlainTextEdit {
            background-color: #1e1e1e; color: #d4d4d4;
            font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
            font-size: 10px; border: 1px solid #444; border-radius: 4px;
            padding: 6px; selection-background-color: #264f78; }""",
        'run_btn': """QPushButton {
            background-color: #28a745; color: white; border: none;
            padding: 8px 16px; border-radius: 4px; font-weight: bold; }
            QPushButton:hover { background-color: #218838; }
            QPushButton:disabled { background-color: #6c757d; }""",
        'path': "color: #888; font-size: 10px; font-family: monospace;",
        'header_title': "color: #2E86AB; font-size: 14px; font-weight: bold;",
        'header_count': "color: #888; font-style: italic;",
        'script_name': "color: #2E86AB; margin-bottom: 4px;",
        'script_file': "color: #888; font-size: 10px; margin-bottom: 2px;",
        'action_btn': """QPushButton {
            background-color: #f0f0f0; border: 1px solid #ccc;
            border-radius: 3px; padding: 5px 12px; }
            QPushButton:hover { background-color: #e0e0e0; }""",
        'close_btn': """QPushButton {
            background-color: #dc3545; color: white; border: none;
            border-radius: 3px; padding: 5px 16px; font-weight: bold; }
            QPushButton:hover { background-color: #c82333; }""",
    }

    def __init__(self, scripts_info, execute_callback, reload_callback=None, parent=None):
        super().__init__(parent)
        self.scripts_info = scripts_info
        self.execute_callback = execute_callback
        self.reload_callback = reload_callback
        self.current_script = None
        self._setup_ui()

    def _setup_ui(self):
        self.setWindowTitle(tr('script_browser'))
        self.setModal(False)
        self.resize(920, 580)
        self.setMinimumSize(640, 400)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 6)
        root.setSpacing(4)

        # --- Header (compact, fixed height) ---
        header_widget = QWidget()
        header_widget.setFixedHeight(28)
        header = QHBoxLayout(header_widget)
        header.setContentsMargins(2, 0, 2, 0)
        header.setSpacing(8)
        title = QLabel(tr('available_scripts'))
        title.setStyleSheet(self._CSS['header_title'])
        self.count_label = QLabel(f"({len(self.scripts_info)} {tr('scripts_found')})")
        self.count_label.setStyleSheet(self._CSS['header_count'])
        header.addWidget(title)
        header.addWidget(self.count_label)
        header.addStretch()
        root.addWidget(header_widget)

        # --- Splitter: List | Details ---
        splitter = QSplitter(QtCompat.get('horizontal'))

        # Left: script list
        self.script_list = QListWidget()
        self.script_list.setStyleSheet("""QListWidget::item { padding: 4px 6px; }
            QListWidget::item:selected { background-color: #2E86AB; color: white; }""")
        self._populate_list()
        self.script_list.currentItemChanged.connect(self._on_script_selected)
        splitter.addWidget(self.script_list)

        # Right: details panel
        right = QWidget()
        details = QVBoxLayout(right)
        details.setContentsMargins(8, 0, 0, 0)
        details.setSpacing(4)

        self.script_name = QLabel(tr('select_script'))
        self.script_name.setFont(QFont("", 12, QtCompat.get('font_bold')))
        self.script_name.setStyleSheet(self._CSS['script_name'])

        self.script_filename = QLabel("")
        self.script_filename.setStyleSheet(self._CSS['script_file'])

        details.addWidget(self.script_name)
        details.addWidget(self.script_filename)

        # Tabs
        self.tab_widget = QTabWidget()
        self.tab_widget.addTab(self._build_desc_tab(), tr('description').rstrip(':'))
        self.tab_widget.addTab(self._build_output_tab(), tr('output'))
        details.addWidget(self.tab_widget)

        splitter.addWidget(right)
        splitter.setSizes([260, 640])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, 1)

        # --- Bottom action bar (all buttons on one line) ---
        self.run_button = QPushButton(tr('execute_script'))
        self.run_button.setEnabled(False)
        self.run_button.clicked.connect(self._run_selected_script)
        self.run_button.setStyleSheet(self._CSS['run_btn'])
        root.addLayout(self._build_action_bar())

        if self.script_list.count() > 0:
            self.script_list.setCurrentRow(0)

    def _build_desc_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(6, 6, 6, 6)

        self.script_description = QTextEdit()
        self.script_description.setReadOnly(True)
        self.script_description.setMaximumHeight(120)
        self.script_description.setStyleSheet(self._CSS['description'])

        self.script_path = QLabel("")
        self.script_path.setWordWrap(True)
        self.script_path.setStyleSheet(self._CSS['path'])

        layout.addWidget(QLabel(tr('description')))
        layout.addWidget(self.script_description)
        layout.addWidget(QLabel(tr('location')))
        layout.addWidget(self.script_path)
        layout.addStretch()
        return tab

    def _build_output_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(6, 6, 6, 6)

        controls = QHBoxLayout()
        controls.addWidget(QLabel(tr('console_output')))
        controls.addStretch()
        clear_btn = QPushButton(tr('clear_output'))
        clear_btn.clicked.connect(self.clear_output)
        clear_btn.setMaximumWidth(100)
        controls.addWidget(clear_btn)
        layout.addLayout(controls)

        self.output_text = QPlainTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setStyleSheet(self._CSS['console'])
        self.output_text.setPlainText("Console output will appear here after script execution...")
        layout.addWidget(self.output_text)
        return tab

    def _build_action_bar(self):
        bar = QHBoxLayout()
        bar.setSpacing(6)

        for text, callback in [
            (tr('refresh_list'), self.refresh_scripts),
            (tr('open_folder'), self.open_scripts_folder),
        ]:
            btn = QPushButton(text)
            btn.setStyleSheet(self._CSS['action_btn'])
            btn.clicked.connect(callback)
            bar.addWidget(btn)

        bar.addStretch()
        bar.addWidget(self.run_button)

        close_btn = QPushButton(tr('close'))
        close_btn.setStyleSheet(self._CSS['close_btn'])
        close_btn.clicked.connect(self.accept)
        bar.addWidget(close_btn)
        return bar

    def _populate_list(self):
        """Fill the script list from scripts_info."""
        self.script_list.clear()
        for filename, info in sorted(self.scripts_info.items()):
            item = QListWidgetItem(info['name'])
            item.setData(QtCompat.get('user_role'), (filename, info))
            self.script_list.addItem(item)

    def _on_script_selected(self, current, previous):
        if current:
            filename, info = current.data(QtCompat.get('user_role'))
            self.script_name.setText(info['name'])
            self.script_filename.setText(f"{tr('file')} {filename}")
            self.script_description.setText(info['description'])
            self.script_path.setText(info['path'])
            self.run_button.setEnabled(True)
            self.current_script = info
        else:
            self.script_name.setText(tr('no_script_selected'))
            self.script_filename.setText("")
            self.script_description.clear()
            self.script_path.setText("")
            self.run_button.setEnabled(False)
            self.current_script = None

    def _run_selected_script(self):
        if not self.current_script:
            return

        self.tab_widget.setCurrentIndex(1)
        self.clear_output()
        name, path = self.current_script['name'], self.current_script['path']

        self.append_output(f"Executing: {name}")
        self.append_output(f"Path: {path}")
        self.append_output("=" * 60)

        try:
            success, output, errors, warnings = self.execute_callback(path, capture_output=True)

            if output:
                self.append_output("--- Output ---")
                self.append_output(output)
            if errors:
                self.append_output("--- Errors ---")
                self.append_output(errors, is_error=True)
            if warnings:
                self.append_output("--- Warnings ---")
                for w in warnings:
                    self.append_output(w, is_warning=True)

            if success:
                msg = tr('script_executed_warnings') if warnings else tr('script_executed')
                self.append_output(f"OK: {msg}")
                show_status_message(f"{msg}: '{name}'", 3000)
            else:
                self.append_output("FAILED: Script execution failed!")

        except Exception as e:
            self.append_output(f"CRITICAL: {str(e)}", is_error=True)
            QMessageBox.critical(self, tr('error'), f"{tr('error_executing')}:\n\n{str(e)}")

    def append_output(self, text, is_error=False, is_warning=False):
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        prefix = "ERR" if is_error else ("WRN" if is_warning else "   ")
        self.output_text.appendPlainText(f"[{ts}] {prefix} {text}")
        scrollbar = self.output_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        QApplication.processEvents()

    def clear_output(self):
        self.output_text.clear()
        self.append_output("Console ready.")

    def refresh_scripts(self):
        if not self.reload_callback:
            return
        self.scripts_info = self.reload_callback()

        # Remember selection
        current = self.script_list.currentItem()
        prev_filename = current.data(QtCompat.get('user_role'))[0] if current else None

        self._populate_list()
        self.count_label.setText(f"({len(self.scripts_info)} {tr('scripts_found')})")

        # Restore selection
        if prev_filename:
            for i in range(self.script_list.count()):
                if self.script_list.item(i).data(QtCompat.get('user_role'))[0] == prev_filename:
                    self.script_list.setCurrentRow(i)
                    return
        if self.script_list.count() > 0:
            self.script_list.setCurrentRow(0)

    def open_scripts_folder(self):
        if self.current_script:
            open_folder(os.path.dirname(self.current_script['path']))


def show_status_message(message, timeout=3000, is_warning=False):
    """Display a temporary message in the QGIS status bar."""
    try:
        iface.mainWindow().statusBar().showMessage(message, timeout)
    except Exception:
        pass


def open_folder(path):
    """Open a folder in the OS file manager."""
    import subprocess, platform
    try:
        system = platform.system()
        if system == "Windows":
            os.startfile(path)
        elif system == "Darwin":
            subprocess.run(["open", path])
        else:
            subprocess.run(["xdg-open", path])
    except Exception as e:
        QMessageBox.information(None, tr('open_scripts_folder'),
                               f"{tr('error_opening_folder')}: {str(e)}")


class ScriptManager:
    """Script Manager plugin class for QGIS"""
    
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.scripts_dir = os.path.join(self.plugin_dir, 'scripts')
        
        if not os.path.exists(self.scripts_dir):
            os.makedirs(self.scripts_dir)
            self.create_example_script()
        
        self.menu = None
        self.scripts = {}
        self.browser_dialog = None
        self.executor = SafeScriptExecutor()
        self.toolbar = None
        self.toolbar_container = None
        self.toolbar_script_buttons = []
        self._validated_acknowledged = set()
        
        self.watcher = ScriptWatcher(self.scripts_dir)
        self.watcher.scripts_changed.connect(self.reload_scripts)
        
        self.reload_timer = QTimer()
        self.reload_timer.setSingleShot(True)
        self.reload_timer.timeout.connect(self.update_menu)
        
        QgsMessageLog.logMessage(f"Script Manager initialized with Qt{QT_VERSION}", 
                                "Script Manager", Qgis.Info)
        
    def initGui(self):
        try:
            self.menu = QMenu(f"📋 {tr('script_manager')}", self.iface.mainWindow().menuBar())
            menubar = self.iface.mainWindow().menuBar()
            menubar.addMenu(self.menu)
            
            self.load_scripts()
            self.create_menu()
            self._create_toolbar()

        except Exception as e:
            QgsMessageLog.logMessage(f"Error initializing GUI: {str(e)}", 
                                   "Script Manager", Qgis.Critical)
            QMessageBox.critical(None, "Script Manager Error", 
                               f"Failed to initialize plugin GUI:\n{str(e)}")
    
    def unload(self):
        try:
            if self.browser_dialog:
                self.browser_dialog.close()
            if self.menu:
                self.menu.clear()
                self.iface.mainWindow().menuBar().removeAction(self.menu.menuAction())
            if self.toolbar:
                self.toolbar.clear()
                self.iface.mainWindow().removeToolBar(self.toolbar)
                self.toolbar = None
            self.toolbar_container = None
            self.toolbar_script_buttons.clear()

            QgsMessageLog.logMessage("Script Manager unloaded successfully",
                                   "Script Manager", Qgis.Info)
        except Exception as e:
            QgsMessageLog.logMessage(f"Error during unload: {str(e)}",
                                   "Script Manager", Qgis.Warning)
    
    def create_example_script(self):
        lang = _translator.current_language
        
        qt_import_template = '''# -*- coding: utf-8 -*-
"""
Qt Compatibility Example for Script Manager
Demonstrates safe script writing with output capture
"""

try:
    from qgis.PyQt.QtWidgets import QMessageBox
    from qgis.PyQt.QtCore import Qt
    QT_VERSION = 6
    print(f"Using Qt6 via QGIS PyQt")
except ImportError:
    try:
        from PyQt6.QtWidgets import QMessageBox
        from PyQt6.QtCore import Qt
        QT_VERSION = 6
        print(f"Using Qt6 directly")
    except ImportError:
        from PyQt5.QtWidgets import QMessageBox
        from PyQt5.QtCore import Qt
        QT_VERSION = 5
        print(f"Using Qt5")

print(f"Qt Version: {QT_VERSION}")
'''
        
        if lang == 'pt_BR':
            example_script = qt_import_template + '''
"""
Script Exemplo PyQGIS
Descrição: Script exemplo que demonstra uso de print e informações das camadas
"""

from qgis.core import QgsProject
from qgis.utils import iface

def main():
    """Função principal do script"""
    print("🚀 Iniciando script exemplo...")
    
    project = QgsProject.instance()
    layers = project.mapLayers()
    layer_count = len(layers)
    
    print(f"📊 Analisando projeto: {project.baseName()}")
    print(f"📁 Número de camadas encontradas: {layer_count}")
    
    if layer_count == 0:
        message = "❌ Nenhuma camada carregada no projeto."
        print(message)
    else:
        print("📋 Lista de camadas:")
        layer_names = []
        for i, (layer_id, layer) in enumerate(layers.items(), 1):
            layer_name = layer.name()
            layer_type = "Vetor" if hasattr(layer, 'geometryType') else "Raster"
            print(f"  {i}. {layer_name} ({layer_type})")
            layer_names.append(f"{layer_name} ({layer_type})")
        
        message = f"✅ Camadas no projeto ({layer_count}):\\n" + "\\n".join(layer_names)
        print(f"📤 Exibindo resultado para o usuário...")
    
    QMessageBox.information(None, "Informações das Camadas", message)
    print("✅ Script executado com sucesso!")

if __name__ == "__main__":
    main()
'''
        else:
            example_script = qt_import_template + '''
"""
PyQGIS Example Script
Description: Example script demonstrating print usage and layer information
"""

from qgis.core import QgsProject
from qgis.utils import iface

def main():
    """Main script function"""
    print("🚀 Starting example script...")
    
    project = QgsProject.instance()
    layers = project.mapLayers()
    layer_count = len(layers)
    
    print(f"📊 Analyzing project: {project.baseName()}")
    print(f"📁 Number of layers found: {layer_count}")
    
    if layer_count == 0:
        message = "❌ No layers loaded in the project."
        print(message)
    else:
        print("📋 Layer list:")
        layer_names = []
        for i, (layer_id, layer) in enumerate(layers.items(), 1):
            layer_name = layer.name()
            layer_type = "Vector" if hasattr(layer, 'geometryType') else "Raster"
            print(f"  {i}. {layer_name} ({layer_type})")
            layer_names.append(f"{layer_name} ({layer_type})")
        
        message = f"✅ Layers in project ({layer_count}):\\n" + "\\n".join(layer_names)
        print(f"📤 Displaying result to user...")
    
    QMessageBox.information(None, "Layer Information", message)
    print("✅ Script executed successfully!")

if __name__ == "__main__":
    main()
'''
        
        example_path = os.path.join(self.scripts_dir, 'layers_example.py')
        with open(example_path, 'w', encoding='utf-8') as f:
            f.write(example_script)
    
    def load_scripts(self):
        self.scripts.clear()
        
        if not os.path.exists(self.scripts_dir):
            return
        
        loaded_count = 0
        error_count = 0
        
        for filename in os.listdir(self.scripts_dir):
            if filename.endswith('.py') and not filename.startswith('__'):
                script_path = os.path.join(self.scripts_dir, filename)
                try:
                    script_info = self.get_script_info(script_path)
                    if script_info:
                        self.scripts[filename] = script_info
                        self.watcher.add_file_to_watch(script_path)
                        loaded_count += 1
                    else:
                        error_count += 1
                except Exception as e:
                    error_count += 1
                    QgsMessageLog.logMessage(f"Error loading script {filename}: {str(e)}", 
                                           "Script Manager", Qgis.Warning)
        
        QgsMessageLog.logMessage(f"Loaded {loaded_count} scripts, {error_count} errors", 
                               "Script Manager", Qgis.Info)
    
    @staticmethod
    def _parse_docstring_field(content, field, as_bool=False):
        """Extract a field value from a script's docstring. Returns match or None/False."""
        pattern = r'(?:"""|\'\'\')\s*[\s\S]*?' + field + r':\s*([^\n]+)'
        match = re.search(pattern, content, re.IGNORECASE)
        if not match:
            return False if as_bool else None
        if as_bool:
            return match.group(1).strip().lower() in ('true', 'yes', '1')
        return match.group(1).strip().replace('"', '').replace("'", "")

    def get_script_info(self, script_path):
        try:
            with open(script_path, 'r', encoding='utf-8') as f:
                content = f.read()

            try:
                compile(content, script_path, 'exec')
            except SyntaxError as e:
                QgsMessageLog.logMessage(f"Syntax error in {script_path}: {str(e)}",
                                       "Script Manager", Qgis.Warning)
                return None

            # Parse all docstring fields
            desc_keys = ('Description', 'Descrição', 'Descripción')
            description = None
            for key in desc_keys:
                description = self._parse_docstring_field(content, key)
                if description:
                    break
            description = description or "PyQGIS Script"

            show_in_toolbar = self._parse_docstring_field(content, 'Toolbar', as_bool=True)
            toolbar_label = self._parse_docstring_field(content, 'ToolbarLabel') if show_in_toolbar else None
            is_validated = self._parse_docstring_field(content, 'Validated', as_bool=True)

            script_name = os.path.splitext(os.path.basename(script_path))[0]

            return {
                'name': script_name.replace('_', ' ').title(),
                'path': script_path,
                'description': description,
                'toolbar': show_in_toolbar,
                'toolbar_label': toolbar_label,
                'validated': is_validated,
            }

        except Exception as e:
            QgsMessageLog.logMessage(f"Error reading script {script_path}: {str(e)}",
                                   "Script Manager", Qgis.Warning)
            return None
    
    def create_menu(self):
        if not self.menu:
            return
        
        try:
            self.menu.clear()

            
            browser_action = QAction(f"🔍 {tr('script_browser')}", self.iface.mainWindow())
            browser_action.setToolTip(tr('tooltip_browser'))
            browser_action.triggered.connect(self.open_script_browser)
            self.menu.addAction(browser_action)

            
            self.menu.addSeparator()
            
            if not self.scripts:
                no_scripts_action = QAction(f"❌ {tr('no_scripts_found')}", self.iface.mainWindow())
                no_scripts_action.setEnabled(False)
                self.menu.addAction(no_scripts_action)

            else:
                quick_menu = self.menu.addMenu(f"⚡ {tr('quick_access')} ({len(self.scripts)} scripts)")
                
                for filename, script_info in sorted(self.scripts.items()):
                    action = QAction(script_info['name'], self.iface.mainWindow())
                    
                    action.hovered.connect(
                        lambda desc=script_info['description'], name=script_info['name']: 
                        show_status_message(f"💡 {name}: {desc}", 5000)
                    )
                    
                    action.triggered.connect(
                        lambda checked, path=script_info['path']: 
                        self.execute_script(path, capture_output=False)
                    )
                    
                    quick_menu.addAction(action)

                
                quick_menu.aboutToHide.connect(lambda: show_status_message("", 1))
            
            self.menu.addSeparator()
            
            reload_action = QAction(f"🔄 {tr('reload_scripts')}", self.iface.mainWindow())
            reload_action.setToolTip(tr('tooltip_reload'))
            reload_action.triggered.connect(self.reload_scripts)
            self.menu.addAction(reload_action)

            
            open_folder_action = QAction(f"📁 {tr('open_scripts_folder')}", self.iface.mainWindow())
            open_folder_action.setToolTip(tr('tooltip_folder'))
            open_folder_action.triggered.connect(self.open_scripts_folder)
            self.menu.addAction(open_folder_action)

            
            info_action = QAction(f"ℹ️ {tr('about')}", self.iface.mainWindow())
            info_action.setToolTip(tr('tooltip_about'))
            info_action.triggered.connect(self.show_info)
            self.menu.addAction(info_action)

            
        except Exception as e:
            QgsMessageLog.logMessage(f"Error creating menu: {str(e)}", 
                                   "Script Manager", Qgis.Critical)
    
    def _create_toolbar(self):
        """Create the toolbar with script buttons, following QGISDualMapViewer pattern."""
        icon_path = os.path.join(self.plugin_dir, "icon.png")

        self.toolbar = self.iface.addToolBar(tr('toolbar_script_manager'))
        self.toolbar.setObjectName("ScriptManagerToolbar")

        self._populate_toolbar(icon_path)

    def _populate_toolbar(self, icon_path=None):
        """Populate (or repopulate) the toolbar container with current scripts."""
        if icon_path is None:
            icon_path = os.path.join(self.plugin_dir, "icon.png")

        # Remove old container if rebuilding
        if self.toolbar_container is not None:
            self.toolbar.clear()
            self.toolbar_container = None
            self.toolbar_script_buttons.clear()

        # Container widget with horizontal layout (DualViewer pattern)
        self.toolbar_container = QWidget()
        layout = QHBoxLayout(self.toolbar_container)
        layout.setContentsMargins(3, 2, 3, 2)
        layout.setSpacing(3)

        self.toolbar_container.setStyleSheet("""
            QWidget {
                border: 1px solid #b0b0b0;
                background: transparent;
            }
        """)

        def add_btn(text, tooltip, callback, stylesheet=None, icon=None, style=None):
            btn = QToolButton()
            btn.setText(text)
            btn.setToolTip(tooltip)
            btn.setCursor(QtCompat.get('pointing_hand'))
            if icon:
                btn.setIcon(icon)
            if style:
                btn.setToolButtonStyle(style)
            if stylesheet:
                btn.setStyleSheet(stylesheet)
            btn.clicked.connect(callback)
            layout.addWidget(btn)
            self.toolbar_script_buttons.append(btn)
            return btn

        SCRIPT_BTN_CSS = """
            QToolButton { background-color: #d4edda; border: 1px solid #28a745;
                          border-radius: 3px; padding: 2px 6px; }
            QToolButton:hover { background-color: #b7dfbf; }
            QToolButton:pressed { background-color: #a3d5ab; }
        """

        # Identity button
        add_btn(tr('toolbar_script_manager'), tr('tooltip_browser'),
                self.open_script_browser,
                icon=QIcon(icon_path), style=QtCompat.get('text_beside_icon'))

        # Dynamic script buttons (only scripts with Toolbar: true)
        for filename, script_info in sorted(self.scripts.items()):
            if not script_info.get('toolbar'):
                continue
            label = script_info.get('toolbar_label') or script_info['name']
            if len(label) > 20:
                label = label[:20] + "..."
            path = script_info['path']
            add_btn(label, f"{script_info['name']}: {script_info['description']}",
                    lambda checked=False, p=path: self.execute_script(p, capture_output=False),
                    stylesheet=SCRIPT_BTN_CSS)

        # Utility buttons
        add_btn(tr('toolbar_reload'), tr('tooltip_reload'), self.reload_scripts)
        add_btn(tr('toolbar_open_folder'), tr('tooltip_folder'), self.open_scripts_folder)

        # Add container to toolbar
        self.toolbar.addWidget(self.toolbar_container)

    def _reload_scripts_for_browser(self):
        """Reload scripts and return updated dict. Used as callback for ScriptBrowserDialog."""
        self.load_scripts()
        self.create_menu()
        self._populate_toolbar()
        return self.scripts

    def open_script_browser(self):
        try:
            if not self.scripts:
                show_status_message(f"⚠️ {tr('no_scripts_warning')}", 3000, True)
                return
            
            if self.browser_dialog:
                self.browser_dialog.close()
            
            self.browser_dialog = ScriptBrowserDialog(
                self.scripts, self.execute_script,
                reload_callback=self._reload_scripts_for_browser,
                parent=self.iface.mainWindow()
            )
            self.browser_dialog.show()
            
            show_status_message(f"📚 {tr('browser_opened')} {len(self.scripts)} scripts", 2000)
            
        except Exception as e:
            QgsMessageLog.logMessage(f"Error opening script browser: {str(e)}", 
                                   "Script Manager", Qgis.Critical)
            QMessageBox.critical(None, "Error", f"Failed to open script browser:\n{str(e)}")
    
    def execute_script(self, script_path, capture_output=False):
        success = False
        captured_output = ""
        captured_errors = ""
        validation_warnings = []
        
        try:
            with open(script_path, 'r', encoding='utf-8') as f:
                script_content = f.read()
            
            validation_warnings = self.executor.validate_script_imports(script_content)

            if validation_warnings and not capture_output:
                # Look up script info to check Validated flag
                script_filename = os.path.basename(script_path)
                script_info = self.scripts.get(script_filename, {})
                is_validated = script_info.get('validated', False)

                # Show warning if: not validated, OR validated but not yet acknowledged this session
                if not is_validated or script_path not in self._validated_acknowledged:
                    warning_text = "\n".join(validation_warnings)
                    reply = QMessageBox.question(
                        None, tr('validation_warnings'),
                        f"{tr('validation_warnings')}:\n\n{warning_text}\n\nContinue execution?",
                        QMessageBox.Yes | QMessageBox.No
                    )
                    if reply == QMessageBox.No:
                        return False
                    # Remember acknowledgement for validated scripts
                    if is_validated:
                        self._validated_acknowledged.add(script_path)
            
            script_globals = self.executor.prepare_safe_namespace(script_path)
            
            original_path = sys.path.copy()
            
            try:
                script_dir = os.path.dirname(script_path)
                if script_dir not in sys.path:
                    sys.path.insert(0, script_dir)
                
                if capture_output:
                    with self.executor.capture_output():
                        exec(script_content, script_globals)
                    captured_output, captured_errors = self.executor.get_captured_output()
                else:
                    exec(script_content, script_globals)
                
                success = True
                
                script_name = os.path.basename(script_path)
                if not capture_output:
                    show_status_message(f"✅ {tr('script_executed').replace('!', '')} '{script_name}'!", 3000)
                    
                QgsMessageLog.logMessage(f"✅ Script executed successfully: {script_name}", 
                                       "Script Manager", Qgis.Success)
                
                if captured_output.strip():
                    QgsMessageLog.logMessage(f"📤 {tr('output_captured')}:\n{captured_output}", 
                                           "Script Manager", Qgis.Info)
            
            finally:
                sys.path = original_path
        
        except Exception as e:
            script_name = os.path.basename(script_path)
            error_msg = f"❌ {tr('error_executing')} {script_name}: {str(e)}"
            detailed_error = f"{error_msg}\n\nDetails:\n{traceback.format_exc()}"
            
            captured_errors = detailed_error
            
            if not capture_output:
                show_status_message(f"❌ {tr('error')} '{script_name}'", 5000, True)
                QMessageBox.critical(None, tr('script_error'), 
                                   f"{tr('error_executing')} '{script_name}':\n\n{str(e)}\n\n{tr('check_log')}")
            
            QgsMessageLog.logMessage(detailed_error, "Script Manager", Qgis.Critical)
        
        if capture_output:
            return success, captured_output, captured_errors, validation_warnings
        else:
            return success
    
    def reload_scripts(self):
        self.reload_timer.start(500)
    
    def update_menu(self):
        try:
            self.load_scripts()
            self.create_menu()
            self._populate_toolbar()
            show_status_message(f"🔄 {tr('scripts_reloaded')} ({len(self.scripts)} scripts)", 2000)
            QgsMessageLog.logMessage("🔄 Scripts reloaded successfully", "Script Manager", Qgis.Info)
        except Exception as e:
            QgsMessageLog.logMessage(f"Error updating menu: {str(e)}", 
                                   "Script Manager", Qgis.Critical)
    
    def open_scripts_folder(self):
        open_folder(self.scripts_dir)

    def show_info(self):
        icon_path = os.path.join(self.plugin_dir, "icon.png")
        scripts_count = len(self.scripts)

        info_text = f"""
<table cellpadding="6"><tr>
<td><img src="{icon_path}" width="48" height="48"></td>
<td>
<span style="font-size:16pt; font-weight:bold;">{tr('about_title')}</span><br>
<span style="color:#666;">{tr('about_subtitle')}</span>
</td>
</tr></table>

<hr>

<p>{tr('about_description')}</p>

<p><b>{tr('about_features')}</b></p>
<ul style="margin-top:2px;">
<li>{tr('about_feature_1')}</li>
<li>{tr('about_feature_2')}</li>
<li>{tr('about_feature_3')}</li>
<li>{tr('about_feature_4')}</li>
<li>{tr('about_feature_5')}</li>
</ul>

<hr>

<table cellpadding="2">
<tr><td><b>{tr('about_scripts_loaded')}:</b></td><td>{scripts_count}</td></tr>
<tr><td><b>{tr('about_scripts_folder')}:</b></td><td><code>{self.scripts_dir}</code></td></tr>
</table>

<hr>

<p><b>{tr('about_docstring_ref')}</b></p>
<pre style="background:#f5f5f5; padding:8px; border:1px solid #ddd;">
Description:  What the script does
Toolbar:      true
ToolbarLabel: Short Name
Validated:    true</pre>

<hr>

<p style="color:#888; font-size:9pt;">
<b>{tr('about_author')}:</b> Thomas W&ouml;lk<br>
<b>{tr('about_original')}:</b> Tiago Jos&eacute; M. Silva
&nbsp;&middot;&nbsp;
<a href="https://github.com/TiagoJoseMS/script-manager">GitHub</a>
&nbsp;&middot;&nbsp;
<a href="https://github.com/TiagoJoseMS/script-manager/issues">Issues</a>
</p>
"""

        dialog = QDialog(self.iface.mainWindow())
        dialog.setWindowTitle(tr('about'))
        dialog.resize(520, 480)
        dialog.setMinimumSize(420, 380)

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 12)

        label = QLabel(info_text)
        label.setTextFormat(QtCompat.get('rich_text'))
        label.setWordWrap(True)
        label.setOpenExternalLinks(True)

        scroll = QScrollArea()
        scroll.setWidget(label)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame if hasattr(QScrollArea, 'NoFrame') else 0)

        ok_button = QPushButton("OK")
        ok_button.setFixedSize(80, 30)
        ok_button.clicked.connect(dialog.accept)

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(ok_button)

        layout.addWidget(scroll)
        layout.addLayout(button_layout)
        dialog.setLayout(layout)

        QtCompat.exec_dialog(dialog)


def classFactory(iface):
    """Return the ScriptManager class instance"""
    return ScriptManager(iface)