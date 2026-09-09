"""Regression tests for the CRS setting, dialog and generated GeoPackages."""

import os
import tempfile
from unittest.mock import patch

from qgis.PyQt.QtWidgets import QDialogButtonBox
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsProject,
    QgsSettings,
    QgsVectorLayer,
)
from qgis.gui import QgsProjectionSelectionWidget

from qcity.core import DatabaseUtils, SETTINGS_MANAGER, SettingsManager
from qcity.gui.qcity_dock import QCityDockWidget
from qcity.gui.qcity_settings_dialog import QCitySettingsDialog
from qcity.test.qcity_test_base import QCityTestBase
from qcity.test.utilities import get_qgis_app


QGIS_APP, CANVAS, IFACE, PARENT = get_qgis_app()


class TestDatabaseCrs(QCityTestBase):
    def setUp(self):
        super().setUp()
        self.settings = QgsSettings()
        self.key = f"{SettingsManager.SETTINGS_KEY}/default_database_crs"
        self.section = QgsSettings.Section.Plugins
        self.had_setting = self.settings.contains(self.key, section=self.section)
        self.previous = self.settings.value(self.key, section=self.section)
        self.settings.remove(self.key, section=self.section)
        self.addCleanup(self.restore_setting)

    def restore_setting(self):
        if self.had_setting:
            self.settings.setValue(self.key, self.previous, section=self.section)
        else:
            self.settings.remove(self.key, section=self.section)

    def custom_crs(self):
        crs = QgsCoordinateReferenceSystem()
        self.assertTrue(
            crs.createFromProj(
                "+proj=tmerc +lat_0=-27.456 +lon_0=153.123 +k=0.9996 "
                "+x_0=500000 +y_0=10000000 +ellps=GRS80 +units=m +no_defs"
            )
        )
        self.assertFalse(crs.authid())
        return crs

    def dialog(self):
        dialog = QCitySettingsDialog()
        self.addCleanup(self.delete_qobject, dialog)
        return dialog

    def assert_package_crs(self, path, expected):
        for name in ("project_areas", "development_sites", "building_levels"):
            with self.subTest(layer=name):
                layer = QgsVectorLayer(f"{path}|layername={name}", name, "ogr")
                self.assertTrue(layer.isValid())
                self.assertEqual(layer.crs(), expected)
                del layer

    def test_default_and_corrupt_settings(self):
        self.assertEqual(SETTINGS_MANAGER.default_database_crs().authid(), "EPSG:7844")
        for value in ("", "not a CRS", "EPSG:99999999", 123, ["EPSG:4326"]):
            with self.subTest(value=value):
                self.settings.setValue(self.key, value, section=self.section)
                self.assertEqual(
                    SETTINGS_MANAGER.default_database_crs().authid(), "EPSG:7844"
                )

    def test_epsg_and_custom_crs_survive_new_manager(self):
        for crs in (QgsCoordinateReferenceSystem("EPSG:7850"), self.custom_crs()):
            with self.subTest(crs=crs.toProj()):
                SETTINGS_MANAGER.set_default_database_crs(crs)
                self.assertEqual(SettingsManager().default_database_crs(), crs)

    def test_invalid_crs_preserves_saved_choice(self):
        expected = QgsCoordinateReferenceSystem("EPSG:7850")
        SETTINGS_MANAGER.set_default_database_crs(expected)
        with self.assertRaises(ValueError):
            SETTINGS_MANAGER.set_default_database_crs(QgsCoordinateReferenceSystem())
        self.assertEqual(SETTINGS_MANAGER.default_database_crs(), expected)

    def test_all_new_layers_use_default_or_selected_crs(self):
        choices = (
            QgsCoordinateReferenceSystem("EPSG:7844"),
            QgsCoordinateReferenceSystem("EPSG:7850"),
            self.custom_crs(),
        )
        for crs in choices:
            with self.subTest(crs=crs.toProj()):
                SETTINGS_MANAGER.set_default_database_crs(crs)
                with tempfile.TemporaryDirectory() as directory:
                    path = os.path.join(directory, "new.gpkg")
                    DatabaseUtils.create_base_tables(path)
                    self.assert_package_crs(path, crs)

    def test_loading_existing_package_preserves_its_crs(self):
        original = QgsCoordinateReferenceSystem("EPSG:7844")
        project = QgsProject.instance()
        project.setCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
        with tempfile.TemporaryDirectory() as directory:
            old_path = os.path.join(directory, "existing.gpkg")
            DatabaseUtils.create_base_tables(old_path)
            SETTINGS_MANAGER.set_default_database_crs(
                QgsCoordinateReferenceSystem("EPSG:7850")
            )
            widget = QCityDockWidget(project, IFACE)
            try:
                widget.load_project_database(old_path)
                self.assert_package_crs(old_path, original)
                self.assertEqual(project.crs().authid(), "EPSG:4326")
            finally:
                project.clear()
                self.delete_qobject(widget)

    def test_dialog_initializes_and_saves_only_on_ok(self):
        dialog = self.dialog()
        self.assertEqual(dialog.crs_widget.crs().authid(), "EPSG:7844")
        dialog.crs_widget.setCrs(QgsCoordinateReferenceSystem("EPSG:7850"))
        self.assertEqual(SETTINGS_MANAGER.default_database_crs().authid(), "EPSG:7844")
        dialog.button_box.button(QDialogButtonBox.StandardButton.Ok).click()
        self.assertEqual(SETTINGS_MANAGER.default_database_crs().authid(), "EPSG:7850")
        reopened = self.dialog()
        self.assertEqual(reopened.crs_widget.crs().authid(), "EPSG:7850")

    def test_cancel_preserves_saved_choice(self):
        dialog = self.dialog()
        dialog.crs_widget.setCrs(QgsCoordinateReferenceSystem("EPSG:7850"))
        dialog.button_box.button(QDialogButtonBox.StandardButton.Cancel).click()
        self.assertEqual(SETTINGS_MANAGER.default_database_crs().authid(), "EPSG:7844")

    def test_dialog_rejects_missing_crs(self):
        dialog = self.dialog()
        dialog.crs_widget.setOptionVisible(QgsProjectionSelectionWidget.CrsNotSet, True)
        dialog.crs_widget.setCrs(QgsCoordinateReferenceSystem())
        self.assertFalse(
            dialog.button_box.button(QDialogButtonBox.StandardButton.Ok).isEnabled()
        )
        dialog.accept()
        self.assertEqual(dialog.result(), 0)
        self.assertEqual(SETTINGS_MANAGER.default_database_crs().authid(), "EPSG:7844")

    def test_dialog_keeps_custom_definition(self):
        expected = self.custom_crs()
        dialog = self.dialog()
        dialog.crs_widget.setCrs(expected)
        dialog.button_box.button(QDialogButtonBox.StandardButton.Ok).click()
        self.assertEqual(self.dialog().crs_widget.crs(), expected)

    def test_settings_button_works_without_loaded_database(self):
        widget = QCityDockWidget(QgsProject.instance(), IFACE)
        try:
            widget.set_widgets_enabled(False)
            self.assertTrue(widget.toolButton_settings.isEnabled())
            with patch.object(QCitySettingsDialog, "exec", return_value=0) as execute:
                widget.toolButton_settings.click()
                execute.assert_called_once()
        finally:
            self.delete_qobject(widget)
