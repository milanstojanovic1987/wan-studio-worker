from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
    QMessageBox, QPushButton, QSpinBox, QSplitter, QTextEdit, QVBoxLayout, QWidget, QInputDialog,
)
from PySide6.QtCore import QUrl

from .generation import run_batch
from .models import Project, Scene
from .runpod import RunPodV2
from .settings import Settings
from .store import ProjectStore


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("RunPod settings")
        self.settings = settings
        form = QFormLayout(self)
        self.image = QLineEdit(settings.worker_image)
        self.gpu = QLineEdit(settings.gpu_id)
        self.cloud = QComboBox(); self.cloud.addItems(["COMMUNITY", "SECURE"]); self.cloud.setCurrentText(settings.cloud)
        self.disk = QSpinBox(); self.disk.setRange(80, 500); self.disk.setValue(settings.disk_gb); self.disk.setSuffix(" GB")
        self.root = QLineEdit(settings.projects_root)
        self.idle = QSpinBox(); self.idle.setRange(300, 3600); self.idle.setValue(settings.idle_exit_seconds); self.idle.setSuffix(" sec")
        form.addRow("Worker image", self.image)
        form.addRow("GPU", self.gpu)
        form.addRow("Cloud", self.cloud)
        form.addRow("Ephemeral disk", self.disk)
        form.addRow("Projects folder", self.root)
        form.addRow("Worker safety idle-exit", self.idle)
        note = QLabel("Persistent storage: DISABLED. Models and temporary files are discarded with the Pod.")
        note.setWordWrap(True); form.addRow(note)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); form.addRow(buttons)

    def accept(self):
        self.settings.worker_image = self.image.text().strip()
        self.settings.gpu_id = self.gpu.text().strip()
        self.settings.cloud = self.cloud.currentText()
        self.settings.disk_gb = self.disk.value()
        self.settings.projects_root = self.root.text().strip()
        self.settings.idle_exit_seconds = self.idle.value()
        self.settings.save()
        super().accept()


class GenerationThread(QThread):
    progress = Signal(str)
    done = Signal(str)
    failed = Signal(str)

    def __init__(self, store: ProjectStore, project: Project, api_key: str, settings: Settings):
        super().__init__()
        self.store, self.project, self.api_key, self.settings = store, project, api_key, settings

    def run(self):
        try:
            message = run_batch(self.store, self.project, self.api_key, self.settings, self.progress.emit)
            self.done.emit(message)
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Wan Studio")
        self.resize(1050, 720)
        self.settings = Settings.load()
        self.store = ProjectStore(Path(self.settings.projects_root))
        self.project: Project | None = None
        self.current_scene: Scene | None = None
        self.thread: GenerationThread | None = None
        self._build()
        self._refresh_projects()

    def _build(self):
        root = QWidget(); outer = QVBoxLayout(root)
        top = QHBoxLayout()
        top.addWidget(QLabel("RunPod API key:"))
        self.api_key = QLineEdit(os.getenv("RUNPOD_API_KEY", "")); self.api_key.setEchoMode(QLineEdit.Password)
        top.addWidget(self.api_key, 1)
        test = QPushButton("Test"); test.clicked.connect(self.test_runpod); top.addWidget(test)
        settings_btn = QPushButton("Settings"); settings_btn.clicked.connect(self.open_settings); top.addWidget(settings_btn)
        outer.addLayout(top)

        project_row = QHBoxLayout()
        self.projects = QComboBox(); self.projects.currentTextChanged.connect(self.load_project)
        project_row.addWidget(QLabel("Project:")); project_row.addWidget(self.projects, 1)
        new_project = QPushButton("New Project"); new_project.clicked.connect(self.new_project); project_row.addWidget(new_project)
        open_folder = QPushButton("Open Folder"); open_folder.clicked.connect(self.open_project_folder); project_row.addWidget(open_folder)
        outer.addLayout(project_row)

        split = QSplitter()
        left = QWidget(); lv = QVBoxLayout(left)
        self.scene_list = QListWidget(); self.scene_list.currentItemChanged.connect(self.scene_selected); lv.addWidget(self.scene_list)
        scene_buttons = QHBoxLayout()
        add = QPushButton("+ Scene"); add.clicked.connect(self.add_scene); scene_buttons.addWidget(add)
        delete = QPushButton("Delete"); delete.clicked.connect(self.delete_scene); scene_buttons.addWidget(delete)
        lv.addLayout(scene_buttons)
        split.addWidget(left)

        right = QWidget(); rv = QVBoxLayout(right)
        form = QFormLayout()
        self.title = QLineEdit(); form.addRow("Scene name", self.title)
        image_row = QHBoxLayout(); self.image_path = QLineEdit(); self.image_path.setReadOnly(True); choose_image = QPushButton("Choose picture"); choose_image.clicked.connect(self.choose_image); image_row.addWidget(self.image_path,1); image_row.addWidget(choose_image)
        form.addRow("Picture", image_row)
        self.preview = QLabel("No image"); self.preview.setAlignment(Qt.AlignCenter); self.preview.setMinimumHeight(200); self.preview.setStyleSheet("border: 1px solid #777;")
        form.addRow(self.preview)
        self.motion = QTextEdit(); self.motion.setPlaceholderText("Example: The camera slowly moves closer while he turns toward the camera."); self.motion.setMaximumHeight(100); form.addRow("Motion prompt", self.motion)
        self.dialogue = QTextEdit(); self.dialogue.setPlaceholderText("Optional. If present, Wan S2V will create a talking scene."); self.dialogue.setMaximumHeight(90); form.addRow("Dialogue", self.dialogue)
        self.voice = QComboBox(); self.voice.addItems(["af_heart", "af_bella", "af_nicole", "am_adam", "am_michael"]); form.addRow("TTS voice", self.voice)
        audio_row = QHBoxLayout(); self.audio_path = QLineEdit(); self.audio_path.setReadOnly(True); choose_audio = QPushButton("Choose audio"); choose_audio.clicked.connect(self.choose_audio); clear_audio = QPushButton("Clear"); clear_audio.clicked.connect(lambda: self.audio_path.setText("")); audio_row.addWidget(self.audio_path,1); audio_row.addWidget(choose_audio); audio_row.addWidget(clear_audio); form.addRow("Or recorded audio", audio_row)
        self.mode = QLabel("Mode: Wan 2.2 Lightning I2V"); form.addRow(self.mode)
        rv.addLayout(form)
        save = QPushButton("Save Scene"); save.clicked.connect(self.save_scene); rv.addWidget(save)
        split.addWidget(right); split.setStretchFactor(1, 2)
        outer.addWidget(split, 1)

        self.generate = QPushButton("GENERATE ALL"); self.generate.setMinimumHeight(48); self.generate.clicked.connect(self.generate_all); outer.addWidget(self.generate)
        self.status = QTextEdit(); self.status.setReadOnly(True); self.status.setMaximumHeight(140); outer.addWidget(self.status)
        self.setCentralWidget(root)
        self.dialogue.textChanged.connect(self.update_mode_label); self.audio_path.textChanged.connect(self.update_mode_label)

    def log(self, text: str):
        self.status.append(text)

    def _refresh_projects(self):
        current = self.projects.currentText()
        self.projects.blockSignals(True); self.projects.clear(); self.projects.addItems(self.store.list_projects()); self.projects.blockSignals(False)
        if current and self.projects.findText(current) >= 0: self.projects.setCurrentText(current)
        elif self.projects.count(): self.projects.setCurrentIndex(0); self.load_project(self.projects.currentText())

    def new_project(self):
        name, ok = QInputDialog.getText(self, "New project", "Project name:")
        if not ok or not name.strip(): return
        try:
            project = self.store.create(name)
            self._refresh_projects(); self.projects.setCurrentText(project.name); self.load_project(project.name)
        except Exception as exc: QMessageBox.critical(self, "Could not create project", str(exc))

    def load_project(self, name: str):
        if not name: return
        try:
            self.project = self.store.load(name); self.current_scene = None; self.refresh_scenes(); self.clear_form()
        except Exception as exc: self.log(f"Could not load project: {exc}")

    def refresh_scenes(self):
        self.scene_list.clear()
        if not self.project: return
        for scene in self.project.scenes:
            item = QListWidgetItem(f"{scene.title}   [{scene.status}]"); item.setData(Qt.UserRole, scene.id); self.scene_list.addItem(item)

    def add_scene(self):
        if not self.project:
            QMessageBox.information(self, "Project", "Create a project first."); return
        scene = Scene(title=f"Scene {len(self.project.scenes)+1}")
        self.project.scenes.append(scene); self.store.save(self.project); self.refresh_scenes(); self.scene_list.setCurrentRow(len(self.project.scenes)-1)

    def scene_selected(self, current, previous):
        if not current or not self.project: return
        scene_id = current.data(Qt.UserRole)
        self.current_scene = next((s for s in self.project.scenes if s.id == scene_id), None)
        if self.current_scene: self.populate(self.current_scene)

    def populate(self, s: Scene):
        self.title.setText(s.title); self.image_path.setText(s.image_path); self.motion.setPlainText(s.motion_prompt); self.dialogue.setPlainText(s.dialogue); self.audio_path.setText(s.audio_path); self.voice.setCurrentText(s.voice); self.show_preview(s.image_path); self.update_mode_label()

    def clear_form(self):
        self.title.clear(); self.image_path.clear(); self.motion.clear(); self.dialogue.clear(); self.audio_path.clear(); self.preview.setText("No image"); self.preview.setPixmap(QPixmap())

    def choose_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose image", "", "Images (*.png *.jpg *.jpeg *.webp)")
        if path: self.image_path.setText(path); self.show_preview(path)

    def choose_audio(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose dialogue audio", "", "Audio (*.wav *.mp3 *.m4a *.flac)")
        if path: self.audio_path.setText(path)

    def show_preview(self, path: str):
        if not path or not Path(path).is_file(): self.preview.setText("No image"); self.preview.setPixmap(QPixmap()); return
        pix = QPixmap(path)
        if pix.isNull(): self.preview.setText("Could not preview image"); return
        self.preview.setPixmap(pix.scaled(520, 260, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def update_mode_label(self):
        speaking = bool(self.dialogue.toPlainText().strip() or self.audio_path.text().strip())
        self.mode.setText("Mode: Wan 2.2 S2V (audio + lip sync)" if speaking else "Mode: Wan 2.2 Lightning I2V")

    def save_scene(self):
        if not self.project or not self.current_scene:
            QMessageBox.information(self, "Scene", "Add or select a scene first."); return
        try:
            s = self.current_scene
            old = (s.title, s.image_path, s.motion_prompt, s.dialogue, s.audio_path, s.voice)
            new_title = self.title.text().strip() or s.title
            new_motion = self.motion.toPlainText().strip()
            new_dialogue = self.dialogue.toPlainText().strip()
            new_voice = self.voice.currentText()
            image_value = s.image_path
            image = self.image_path.text().strip()
            if image and Path(image).is_file() and Path(image).resolve() != Path(s.image_path or ".").resolve():
                image_value = self.store.import_asset(self.project, image, s, "image")
            audio_value = s.audio_path
            audio = self.audio_path.text().strip()
            if audio:
                if Path(audio).is_file() and Path(audio).resolve() != Path(s.audio_path or ".").resolve():
                    audio_value = self.store.import_asset(self.project, audio, s, "audio")
            else:
                audio_value = ""
            new = (new_title, image_value, new_motion, new_dialogue, audio_value, new_voice)
            s.title, s.image_path, s.motion_prompt, s.dialogue, s.audio_path, s.voice = new
            if new != old:
                s.status = "pending"; s.output_path = ""; s.remote_job_id = ""; s.error = ""
            self.store.save(self.project); self.refresh_scenes(); self.populate(s); self.log(f"Saved {s.title}.")
        except Exception as exc: QMessageBox.critical(self, "Save failed", str(exc))

    def delete_scene(self):
        if not self.project or not self.current_scene: return
        self.project.scenes = [s for s in self.project.scenes if s.id != self.current_scene.id]; self.current_scene = None; self.store.save(self.project); self.refresh_scenes(); self.clear_form()

    def test_runpod(self):
        try: self.log(RunPodV2(self.api_key.text()).test_connection())
        except Exception as exc: self.log(f"Connection failed: {type(exc).__name__}: {exc}")

    def open_settings(self):
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec(): self.store = ProjectStore(Path(self.settings.projects_root)); self._refresh_projects()

    def open_project_folder(self):
        if self.project: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.store.project_dir(self.project.name))))
        else: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.store.root)))

    def generate_all(self):
        if not self.project: QMessageBox.information(self, "Project", "Create a project first."); return
        self.save_scene() if self.current_scene else None
        if not self.api_key.text().strip(): QMessageBox.warning(self, "RunPod", "Enter your RunPod API key."); return
        self.generate.setEnabled(False); self.log("Starting batch...")
        self.thread = GenerationThread(self.store, self.project, self.api_key.text().strip(), self.settings)
        self.thread.progress.connect(self.log)
        self.thread.done.connect(self.generation_done)
        self.thread.failed.connect(self.generation_failed)
        self.thread.start()

    def generation_done(self, message: str):
        self.log(message); self.generate.setEnabled(True); self.project = self.store.load(self.project.name); self.refresh_scenes()

    def generation_failed(self, message: str):
        self.log("FAILED: " + message); self.generate.setEnabled(True); self.project = self.store.load(self.project.name); self.refresh_scenes()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Wan Studio")
    window = MainWindow(); window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
