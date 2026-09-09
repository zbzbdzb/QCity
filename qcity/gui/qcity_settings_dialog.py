"""User settings for QCity."""

from qgis.PyQt.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
)
from qgis.gui import QgsProjectionSelectionWidget

from qcity.core.settings import SETTINGS_MANAGER


class QCitySettingsDialog(QDialog):
    """Choose the coordinate reference system for new databases."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("QCity Settings"))
        layout = QVBoxLayout(self)
        explanation = QLabel(
            self.tr(
                "Choose a coordinate reference system for new QCity packages. "
                "Existing packages and the QGIS project keep their current CRS."
            ),
            self,
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)

        self.crs_widget = QgsProjectionSelectionWidget(self)
        self.crs_widget.setCrs(SETTINGS_MANAGER.default_database_crs())
        form = QFormLayout()
        form.addRow(self.tr("New package CRS"), self.crs_widget)
        layout.addLayout(form)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        layout.addWidget(self.button_box)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.crs_widget.crsChanged.connect(self._update_ok_button)
        self._update_ok_button()

    def _update_ok_button(self):
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(
            self.crs_widget.crs().isValid()
        )

    def accept(self):
        crs = self.crs_widget.crs()
        if not crs.isValid():
            return
        SETTINGS_MANAGER.set_default_database_crs(crs)
        super().accept()
