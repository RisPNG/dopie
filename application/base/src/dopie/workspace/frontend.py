from __future__ import annotations

import json
import sys
from pathlib import Path

from PySide6.QtCore import QProcess, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from dopie.models import SliceManifest
from dopie.slices.runtime import SliceRuntime
from dopie.workspace.backend import EnvironmentPlan, SliceEnvironmentManager


class StandardSliceWidget(QWidget):
    def __init__(self, manifest: SliceManifest, environments: Path, assets: Path, worker: Path):
        super().__init__()
        self.manifest = manifest
        self.worker = worker
        self.asset_root = assets / manifest.id / manifest.version
        self.environment_manager = SliceEnvironmentManager(environments)
        self.fields: dict[str, QWidget] = {}
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.read_process_output)
        self.process.finished.connect(self.process_finished)
        self.commands: list[tuple[str, ...]] = []
        self.plan: EnvironmentPlan | None = None
        self.phase = "idle"
        self.output_buffer = ""
        layout = QVBoxLayout(self)
        form = QFormLayout()
        for definition in manifest.inputs:
            field_id = str(definition["id"])
            field_type = str(definition.get("type", "text"))
            label = str(definition.get("label", field_id))
            if field_type == "multiline":
                widget = QPlainTextEdit()
                widget.setPlaceholderText(str(definition.get("placeholder", "")))
            elif field_type == "password":
                widget = QLineEdit(str(definition.get("default", "")))
                widget.setEchoMode(QLineEdit.Password)
                widget.setPlaceholderText(str(definition.get("placeholder", "")))
            elif field_type == "integer":
                widget = QSpinBox()
                widget.setRange(int(definition.get("minimum", -2147483648)), int(definition.get("maximum", 2147483647)))
                widget.setValue(int(definition.get("default", 0)))
            elif field_type == "choice":
                widget = QComboBox()
                widget.addItems([str(choice) for choice in definition.get("choices", [])])
            elif field_type == "boolean":
                widget = QCheckBox()
                widget.setChecked(bool(definition.get("default", False)))
            elif field_type in {"file", "directory"}:
                row = QWidget()
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(0, 0, 0, 0)
                widget = QLineEdit()
                browse = QPushButton("Browse")
                if field_type == "file":
                    browse.clicked.connect(
                        lambda checked=False, target=widget: target.setText(QFileDialog.getOpenFileName(self)[0])
                    )
                else:
                    browse.clicked.connect(
                        lambda checked=False, target=widget: target.setText(QFileDialog.getExistingDirectory(self))
                    )
                row_layout.addWidget(widget, 1)
                row_layout.addWidget(browse)
                form.addRow(label, row)
                self.fields[field_id] = widget
                continue
            else:
                widget = QLineEdit(str(definition.get("default", "")))
                widget.setPlaceholderText(str(definition.get("placeholder", "")))
            form.addRow(label, widget)
            self.fields[field_id] = widget
        controls = QHBoxLayout()
        self.run_button = QPushButton("Run")
        self.run_button.setObjectName("primary")
        self.run_button.clicked.connect(self.start_execution)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_execution)
        controls.addStretch()
        controls.addWidget(self.cancel_button)
        controls.addWidget(self.run_button)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.status = QLabel("Ready")
        self.status.setObjectName("subtitle")
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("Execution logs will appear here")
        layout.addLayout(form)
        layout.addLayout(controls)
        layout.addWidget(self.progress)
        layout.addWidget(self.status)
        layout.addWidget(self.log, 1)

    def start_execution(self) -> None:
        inputs: dict[str, object] = {}
        for definition in self.manifest.inputs:
            field_id = str(definition["id"])
            field_type = str(definition.get("type", "text"))
            widget = self.fields[field_id]
            if field_type == "multiline":
                inputs[field_id] = widget.toPlainText()
            elif field_type == "integer":
                inputs[field_id] = widget.value()
            elif field_type == "choice":
                inputs[field_id] = widget.currentText()
            elif field_type == "boolean":
                inputs[field_id] = widget.isChecked()
            else:
                inputs[field_id] = widget.text()
            if definition.get("required") and inputs[field_id] in {"", None}:
                self.status.setText(f"{definition.get('label', field_id)} is required.")
                return
        self.inputs = inputs
        self.log.clear()
        self.progress.setValue(0)
        self.status.setText("Preparing Slice environment…")
        self.run_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.plan = self.environment_manager.prepare_slice_environment(self.manifest)
        self.commands = list(self.plan.commands)
        if self.manifest.assets:
            self.commands.append((sys.executable, str(self.worker), "--prepare-assets", str(self.asset_root)))
        self.phase = "preparing"
        self.start_next_process()

    def start_next_process(self) -> None:
        if self.commands:
            command = self.commands.pop(0)
            self.process.start(command[0], list(command[1:]))
            if "--prepare-assets" in command:
                self.process.write(json.dumps(self.manifest.assets).encode("utf-8"))
                self.process.closeWriteChannel()
            return
        if self.phase == "preparing" and self.plan is not None:
            if self.plan.marker is not None:
                self.plan.marker.write_text("ready", encoding="utf-8")
            self.phase = "running"
            self.status.setText("Running…")
            self.inputs["_assets"] = {
                definition["id"]: str(self.asset_root / definition["id"]) for definition in self.manifest.assets
            }
            self.process.start(
                str(self.plan.python),
                [str(self.worker), str(self.manifest.path), str(self.manifest.operation)],
            )
            self.process.write(json.dumps(self.inputs).encode("utf-8"))
            self.process.closeWriteChannel()

    def read_process_output(self) -> None:
        self.output_buffer += bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        while "\n" in self.output_buffer:
            line, self.output_buffer = self.output_buffer.split("\n", 1)
            if not line:
                continue
            if self.phase == "preparing":
                self.log.appendPlainText(line)
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                self.log.appendPlainText(line)
                continue
            if event["type"] == "progress":
                self.progress.setValue(int(event["value"]))
                self.status.setText(str(event.get("message") or "Running…"))
            elif event["type"] == "log":
                self.log.appendPlainText(str(event["message"]))
            elif event["type"] == "result":
                self.progress.setValue(100)
                self.status.setText("Completed")
                value = event.get("value")
                self.log.appendPlainText(value if isinstance(value, str) else json.dumps(value, indent=2))
            elif event["type"] == "error":
                self.status.setText(f"Failed: {event['message']}")

    def process_finished(self, exit_code: int) -> None:
        self.read_process_output()
        if self.phase == "preparing" and exit_code == 0:
            self.start_next_process()
            return
        if exit_code != 0 and not self.status.text().startswith("Failed"):
            self.status.setText(f"Failed with exit code {exit_code}")
        self.phase = "idle"
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)

    def cancel_execution(self) -> None:
        self.process.kill()
        self.commands.clear()
        self.phase = "idle"
        self.status.setText("Cancelled")
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)


class WorkspacePage(QWidget):
    close_requested = Signal()

    def __init__(self, manifest: SliceManifest, environments: Path, assets: Path, worker: Path):
        super().__init__()
        self.setObjectName("page")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 20, 28, 24)
        back = QPushButton("Back to Library")
        back.clicked.connect(self.close_requested)
        if manifest.interface == "standard":
            content = StandardSliceWidget(manifest, environments, assets, worker)
        else:
            content = SliceRuntime().open_slice(manifest)
        layout.addWidget(back, 0, Qt.AlignLeft)
        layout.addWidget(content, 1)
