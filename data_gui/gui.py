import sys
import pyqtgraph as pg
from PySide6.QtCore import (QDateTime, QDir, QLibraryInfo, QSysInfo, Qt,
                            QTimer, Slot, qVersion, QTimer, QObject)
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, 
                               QVBoxLayout, QLabel, QTabWidget, QHBoxLayout, QComboBox, QStyleFactory,
                               QDial, QGroupBox, QCheckBox, QSizePolicy, QSlider, QSpinBox,
                               QCheckBox, QPushButton, QTextEdit, QLCDNumber, QLineEdit, QGridLayout)
from PySide6.QtGui import QWheelEvent, QPalette, QColor

import numpy as np
import numpy_indexed as npi
from scipy.integrate import simpson
import time
import labrad
import tempfile
from si_prefix import si_format, si_parse
from enum import Enum
import json
from itertools import groupby

def decode_bytes_to_numpy(data_bytes):
    rec = tempfile.TemporaryFile()
    rec.write(data_bytes)
    rec.seek(0)
    numpy_rec = np.load(rec)
    return numpy_rec['data']

def encode_data_numpy_to_bytes(self):
    send = tempfile.TemporaryFile()
    np.savez_compressed(send, data = self.data)
    send.seek(0)
    return send.read()

def test():
    print("test")

class testSignals(QObject):

    def __init__(self):
        self.timer = QTimer()
        self.timer.timeout.connect(self.tick)
        self.start()

    def tick(self):
        print("tick")

    def getData(self):
        return time.strftime('%H:%M:%S')

    def start(self):
        self.timer.start(1000)

    def stop(self):
        self.timer.stop()

class testConnection():
    def receiveMe(self):
        print('time: ' + self.test.getData())

    def __init__(self):
        self.test = testSignals()
        self.test.timer.timeout.connect(self.receiveMe)


def signal_emitted(*args):
    print(f"Signal emitted with args: {args}")

@Slot(str)
def change_style(style_name):
    print(f"Changing style to: {style_name}")
    QApplication.setStyle(QStyleFactory.create(style_name))

def init_widget(w, name, tooltip):
    """Init a widget for the gallery, give it a tooltip showing the
       class name"""
    w.setObjectName(name)
    w.setToolTip(tooltip)

class SingleClickDial(QDial):
    def __init__(self, parent=None):
        super().__init__(parent)

    # Override the wheelEvent to customize the step size
    def wheelEvent(self, event: QWheelEvent):
        # Get the amount of scrolling in terms of "degrees"
        delta = event.angleDelta().y() / 8
        steps = delta / 15  # One step is 15 degrees
        
        # Adjust this value to control how much the dial moves per step
        step_size = 1
        
        # Calculate the new value by applying the step_size to steps
        self.setValue(self.value() + step_size * int(steps))

        # Accept the event so no further handling happens
        event.accept()

class SideTabWidget(QTabWidget):
    def __init__(self):
        super().__init__()

        # Set the tab position to the left
        self.setTabPosition(QTabWidget.West)

        # Create individual tab widgets
        self.tab1 = QWidget()
        self.tab2 = QWidget()
        self.tab3 = QWidget()

        # Set up the layout and contents for Tab 1
        self.tab1_layout = QVBoxLayout()
        self.tab1.setLayout(self.tab1_layout)

        # Set up the layout and contents for Tab 2
        self.tab2_layout = QVBoxLayout()
        self.tab2.setLayout(self.tab2_layout)

        # Set up the layout and contents for Tab 3
        self.tab3_layout = QVBoxLayout()
        self.tab3.setLayout(self.tab3_layout)

        # Add the tabs to the QTabWidget
        self.addTab(self.tab1, "Oscilloscope")
        self.addTab(self.tab2, "Integral View")
        self.addTab(self.tab3, "Settings")

class SettingsTab():
    def __init__(self, TabWidget):
        self.TabWidget = TabWidget
        self.CreateStyleSelector()

        self.top_layout = QHBoxLayout()
        self.top_layout.addWidget(self._style_label)
        self.top_layout.addWidget(self._style_combobox)
        self.top_layout.addStretch(1)

        self.lines_layout = QVBoxLayout()
        self.lines_layout.addLayout(self.top_layout)
        self.lines_layout.addStretch(1)

        self.TabWidget.addLayout(self.lines_layout)

    def style_names(self):
        """Return a list of styles, default platform style first"""
        default_style_name = QApplication.style().objectName().lower()
        result = []
        for style in QStyleFactory.keys():
            if style.lower() == default_style_name:
                result.insert(0, style)
            else:
                result.append(style)
        return result


    def CreateStyleSelector(self):
        self._style_combobox = QComboBox()
        init_widget(self._style_combobox, "StyleSelector", "Visual style selection")
        self._style_combobox.addItems(self.style_names())

        self._style_label = QLabel("Style:")
        init_widget(self._style_label, "", "Visual style selection")
        self._style_label.setBuddy(self._style_combobox)

        self._style_combobox.textActivated.connect(change_style)

class ColorBoxWidget(QWidget):
    def __init__(self, r, g, b, parent=None):
        super().__init__(parent)
        # Set the background color using RGB values
        palette = self.palette()
        palette.setColor(QPalette.Window, QColor(r, g, b))
        self.setPalette(palette)
        self.setAutoFillBackground(True)
        self.setFixedHeight(24)  # Fix the height, width can adjust automatically

colors = [
            (255, 0, 0, 50),   # Red
            (0, 255, 0, 50),   # Green
            (0, 0, 255, 50),   # Blue
            (0, 255, 255, 50), # Cyan
            (255, 0, 255, 50), # Magenta
            (255, 255, 0, 50), # Yellow
            (255, 165, 0, 50), # Orange
            (128, 0, 128, 50), # Purple
            (165, 42, 42, 50)  # Brown
        ]
color_names = [
            "Red",
            "Green",
            "Blue",
            "Cyan",
            "Magenta",
            "Yellow",
            "Orange",
            "Purple",
            "Brown"
        ]

tagging_enum = Enum('tag state', 
             [
                ('NO_TAG', 0),
                ('TAG_READY', 1),
                ('WAVEFORM_TAGGED', 2),
                ('WAVEFORM_NOT_SENT', 3),
                ('TAG_EXPIRED', 4),
             ])

class waveform_tag_group():
    def __init__(self):
        w = 125
        self.control_group = QGroupBox("Tag Info")
        self.control_group.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.layout = QVBoxLayout()
        self.layout.addWidget(QLabel("ARTIQ RID"))
        self.RID_display = QLCDNumber()
        self.RID_display.setDigitCount(6)
        self.RID_display.setFixedWidth(w)
        self.beautify_LCD()
        self.layout.addWidget(self.RID_display)
        self.layout.addWidget(QLabel("Timestamp"))
        self.timestamp_display = QLineEdit()
        self.timestamp_display.setFixedWidth(w)
        self.timestamp_display.setReadOnly(True)
        self.layout.addWidget(self.timestamp_display)
        self.sweep_param_name_label = QLabel("")
        self.sweep_param_name_row = QHBoxLayout()
        self.sweep_param_name_row.addWidget(QLabel("Sweep Param: "))
        self.sweep_param_name_row.addWidget(self.sweep_param_name_label)
        self.layout.addLayout(self.sweep_param_name_row)
        self.sweep_param_display = QLineEdit()
        self.sweep_param_display.setFixedWidth(w)
        self.sweep_param_display.setReadOnly(True)
        self.layout.addWidget(self.sweep_param_display)
        self.control_group.setLayout(self.layout)

        # Tag-related
        self.rid = None
        self.timestamp = None
        self.sweep_param = None
        self.tag_info = None

    def update(self, tag_state, json_tag):
        if tag_state == tagging_enum.WAVEFORM_TAGGED.value:
            self.tag_info = json.loads(json_tag)
            self.rid = self.tag_info['RID']
            self.timestamp = self.tag_info['timestamp']
            self.sweep_param = self.tag_info['SweepParam']
        else:
            print(tagging_enum(tag_state), self.tag_info)
            no_tag_text = "-"
            self.rid = 0
            self.timestamp = no_tag_text
            self.sweep_param = no_tag_text
        self.RID_display.display(self.rid)
        self.timestamp_display.setText(self.timestamp)
        if type(self.sweep_param) == float:
            self.sweep_param_display.setText("%.8g" % self.sweep_param)
        else:
            self.sweep_param_display.setText(str(self.sweep_param))

    def beautify_LCD(self):
        self.RID_display.setStyleSheet("""QLCDNumber {background-color: black; color: white; }""")

class OscilloscopeTab():
    def __init__(self, TabWidget, cxn, integral_tab):
        self.TabWidget = TabWidget
        self.cxn = cxn
        self.integral_tab = integral_tab

        self.integral_tab.init_traces(1)

        # Oscilloscope Label
        osci_label = QLabel("Picoscope 5444D MSO: ")
        self.osci_state_label = QLabel("Not Connected")
        init_widget(osci_label, "", "TODO More Oscilloscope Info")

        # Create the oscilloscope plot area
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.showGrid(x = True, y = True, alpha = 0.3)

        # Generate some random data for the example
        self.traces = list()
        x = np.linspace(0, 10, 1000)
        y = np.sin(x) + np.random.normal(size=x.shape) * 0.1
        self.traces.append(Trace(self.plot_widget, 0, "Channel A", x, y, (255, 255, 255), {}))
        self.x = self.traces[0].x
        self.y = self.traces[0].y
        self.traces[0].plot()
        self.trigger_line = self.plot_widget.addLine(x = None, y = 0.0)
        self.n_samples = 1e+4

        # Timebase control section
        self.timebase_scale_selector = QComboBox()
        self.timebase_delay_selector = SingleClickDial()
        self.timebase_delay_selector.setRange(-5, 5)
        self.timebase_delay_selector.setValue(0)
        self.timebase_delay_selector.setNotchesVisible(True)

        # Layouts
        self.top_layout = QVBoxLayout()
        self.top_banner = QHBoxLayout()
        self.top_banner.addWidget(osci_label)
        self.top_banner.addWidget(self.osci_state_label)
        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self.init_picoscope)
        self.top_banner.addStretch(1)
        self.top_banner.addWidget(self.connect_button)
        self.top_layout.addLayout(self.top_banner)
        self.osci_layer = QHBoxLayout()
        self.osci_layer.addWidget(self.plot_widget)

        self.control_col1 = QVBoxLayout()
        self.control_col1.addWidget(QLabel("Samples:"))
        self.samples_selector = QSpinBox()
        self.samples_selector.setMaximum(1e+5)
        self.samples_selector.setMinimum(1e+3)
        self.samples_selector.setSingleStep(1e+3)
        self.samples_selector.setValue(self.n_samples)
        self.samples_selector.valueChanged.connect(self.init_timebase)
        self.control_col1.addWidget(self.samples_selector)
        self.control_col1.addWidget(QLabel("Averages:"))
        self.averaging_selector = QSpinBox()
        self.averaging_selector.setMaximum(1e+3)
        self.averaging_selector.setMinimum(1)
        self.averaging_selector.setSingleStep(1)
        self.averaging_selector.valueChanged.connect(self.update_averages)
        self.control_col1.addWidget(self.averaging_selector)
        self.control_col1.addWidget(QLabel("Trig. Holdoff (ns):"))
        self.holdoff_selector = QSpinBox()
        self.holdoff_selector.setMaximum(1e+9)
        self.holdoff_selector.setMinimum(-1e+9)
        self.holdoff_selector.setSingleStep(50)
        self.holdoff_selector.valueChanged.connect(self.init_timebase)
        self.control_col1.addWidget(self.holdoff_selector)
        self.timebase_group = QGroupBox("Timebase control")
        self.timebase_layout = QVBoxLayout()
        self.timebase_layout.addWidget(QLabel("Timebase"))
        self.timebase_layout.addWidget(self.timebase_scale_selector)
        self.timebase_layout.addWidget(QLabel("Horizontal Offset"))
        self.timebase_layout.addWidget(self.timebase_delay_selector)
        self.timebase_group.setLayout(self.timebase_layout)
        self.control_col1.addWidget(self.timebase_group)
        self.trigger_control_group = trigger_control_group(self.draw_hline)
        self.control_col1.addWidget(self.trigger_control_group.control_group)

        self.equiscale_button = QCheckBox()
        self.normalization_button = QCheckBox()
        self.normalization_button.checkStateChanged.connect(self.integral_tab.reset_traces)
        self.run_button = QCheckBox()
        self.run_button.checkStateChanged.connect(self.run_or_stop)

        self.force_background_ROI = QCheckBox()
        self.force_background_ROI.checkStateChanged.connect(self.back_ROI)

        self.button_bank = QGroupBox("Control Buttons")
        self.button_bank.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.buttons_grid = QGridLayout()
        self.buttons_grid.addWidget(QLabel("Run: "), 0, 0)
        self.buttons_grid.addWidget(self.run_button, 0, 1)
        self.buttons_grid.addWidget(QLabel("Normalize integral: "), 1, 0)
        self.buttons_grid.addWidget(self.normalization_button, 1, 1)
        self.buttons_grid.addWidget(QLabel("Equiscale: "), 2, 0)
        self.buttons_grid.addWidget(self.equiscale_button)
        self.buttons_grid.addWidget(QLabel("ROI1 as background: "), 3, 0)
        self.buttons_grid.addWidget(self.force_background_ROI, 3, 1)
        self.background_choser = QPushButton("Set as background")
        self.buttons_grid.addWidget(self.background_choser, 4, 0, 4, 1)
        self.background_choser.clicked.connect(self.set_background)
        self.button_bank.setLayout(self.buttons_grid)
        self.control_col1.addWidget(self.button_bank)

        self.tag_display = waveform_tag_group()
        self.control_col1.addWidget(self.tag_display.control_group)
        self.control_col1.addStretch(1)
        self.osci_layer.addLayout(self.control_col1)

        # ROI Controls
        self.control_col2 = QVBoxLayout()
        self.channel_controls = []
        self.osci_layer.addLayout(self.control_col2)

        self.top_layout.addLayout(self.osci_layer)

        # ROI Spinbox Controls
        self.ROI_control = QHBoxLayout()

        # Reset ROIs
        self.reset_button = QPushButton("Reset ROIs")
        self.reset_button.clicked.connect(self.reset_rois)
        self.ROI_control.addWidget(self.reset_button)

        # Checkbox to lock/unlock ROIs
        self.lock_checkbox = QCheckBox("Lock ROIs")
        self.lock_checkbox.stateChanged.connect(self.toggle_lock_rois)
        self.ROI_control.addWidget(self.lock_checkbox)

        self.ROI_control.addWidget(QLabel("      Integration Channel: "))
        self.integration_channel = QComboBox()
        self.integration_channel.addItems(['A', 'B', 'C', 'D'])
        self.ROI_control.addWidget(self.integration_channel)

        self.n_ROIs_label = QLabel("      Number of Integration ROIs: ")
        self.ROI_control.addWidget(self.n_ROIs_label)

        self.n_ROIs = QSpinBox()
        self.n_ROIs.setMinimum(1)
        self.n_ROIs.setMaximum(9)
        self.n_ROIs.valueChanged.connect(self.update_rois)  # Signal connection for value change
        self.ROI_control.addWidget(self.n_ROIs)

        self.ROI_control.addWidget(QLabel("      Integral Source:"))
        self.integral_source = QComboBox()
        self.integral_source.addItems(['A', 'B', 'C', 'D'])
        self.ROI_control.addWidget(self.integral_source)

        self.ROI_control.addWidget(QLabel("      Monitor ROI:"))
        self.ROI_monitor = QSpinBox()
        self.ROI_monitor.setMinimum(1)
        self.ROI_monitor.setMaximum(9)
        self.ROI_control.addWidget(self.ROI_monitor)

        self.ROI_control.addWidget(QLabel("      Integral:"))
        self.integral_value = QLabel("")
        self.ROI_control.addWidget(self.integral_value)
        self.ROI_control.addStretch(1)

        self.send_integral = QPushButton("Send Integral")
        self.ROI_control.addWidget(self.send_integral)

        self.top_layout.addLayout(self.ROI_control)

        # Initialize dynamic ROIs
        # Define a list of colors for the ROIs
        self.colors = colors
        self.color_names = color_names
        self.rois = []
        self.update_rois()

        # Create a widget to contain the layout
        self.container_widget = QWidget()
        self.container_widget.setLayout(self.top_layout)

        # Add the container widget to the TabWidget instead of the layout directly
        self.TabWidget.layout().addWidget(self.container_widget)

        self.prev_raw_data = b'none'

        self.connected = False
        self.running = False
        self.ps_server = self.cxn.ps5444dmso
        self.trigger_level = 0.0

        self.averages = 1
        self.tag_state = tagging_enum.NO_TAG
        self.waveform_tag = ''

        self.integrate_curve()
        self.send_integral.clicked.connect(self.integrate_curve(send_integral = True))
        self.minus_background = False

    def back_ROI(self):
        if self.running:
            if self.force_background_ROI.isChecked():
                if self.n_ROIs.value == 1:
                    self.n_ROIs.setValue(2)
                    self.update_rois()
                self.n_ROIs.setMinimum(2)
            else:
                self.n_ROIs.setMinimum(1)
        else:
            self.force_background_ROI.setChecked(False)

    def set_background(self):
        if self.running:
            if self.minus_background:
                self.minus_background = False
                self.background_choser.setText("Set as background")
                for trace in self.traces:
                    # Order must be preserved!!
                    # trace.reset_average()
                    trace.delete_background()
            else:
                for trace in self.traces:
                    # Order must be preserved!!
                    trace.set_background()
                    # trace.reset_average()
                self.minus_background = True
                self.background_choser.setText("Replace background")

    def update_averages(self, averages):
        self.averages = self.averaging_selector.value()

    def hex2rgb(self, h: str):
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

    def calculate_holdoff(self):
        if self.holdoff_selector.value() >= 0:
            holdoff_samples = round(1e-9 * float(self.holdoff_selector.value()) \
                / float(self.timebase_sampling_rate_8bit(self.timebase)))
            self.pre_trigger_samples = 0
            self.pst_trigger_samples = self.n_samples
        else:
            holdoff_samples = 0
            self.pre_trigger_samples = -round(1e-9 * float(self.holdoff_selector.value()) \
                / float(self.timebase_sampling_rate_8bit(self.timebase)))
            self.pre_trigger_samples = min(self.n_samples, self.pre_trigger_samples)
            self.pst_trigger_samples = self.n_samples - self.pre_trigger_samples
        return holdoff_samples

    def run_or_stop(self):
        if self.connected:
            if self.run_button.isChecked():
                self.running = True
                self.set_enablings(False)
                # Update timebase and trigger
                tb_idx = self.timebase_scale_selector
                holdoff_samples = self.calculate_holdoff()
                self.ps_server.set_pre_trigger_samples(self.pre_trigger_samples)
                self.ps_server.set_timebase(int(self.timebase), int(self.n_samples))
                self.ps_server.set_trigger(
                     self.trigger_control_group.trig_channel_selector.currentIndex(),
                     self.trigger_level,
                     self.trigger_control_group.trig_mode.currentText(),
                     int(holdoff_samples)
                    )
                print("Trigger: ",
                     self.trigger_control_group.trig_channel_selector.currentIndex(),
                     self.trigger_level,
                     self.trigger_control_group.trig_mode.currentText()
                     )
                for cc in self.channel_controls:
                    self.enable_checkbox_changed(cc.idx)
                self.ps_server.run_loop()
                self.reset_traces(-1)
            else:
                self.running = False
                self.ps_server.stop_loop()
                self.set_enablings(True)

    def set_enablings(self, enable):
        for cc in self.channel_controls:
            # cc.voltage_scale_selector.setEnabled(enable)
            cc.enable_button.setEnabled(enable)
        self.trigger_control_group.trig_channel_selector.setEnabled(enable)
        self.trigger_control_group.slider.setEnabled(enable)
        # self.samples_selector.setEnabled(enable)


    def init_picoscope(self):
        if not self.connected:
            print("Initiating picoscope connection ...")

            # Initiate control groups
            self.valid_voltage_scales = decode_bytes_to_numpy(self.ps_server.valid_voltage_scales())
            self.valid_voltage_scale_names = self.ps_server.valid_voltage_scale_names()
            self.ps_voltage_ranges = list(self.valid_voltage_scale_names.split(','))
            print(self.ps_voltage_ranges)
            self.range_names = []
            for vr in self.ps_voltage_ranges:
                self.range_names.append(vr.split(':')[0])
            channel_colors = []
            channel_colors.append(self.hex2rgb("E03616"))
            channel_colors.append(self.hex2rgb("FFF689"))
            channel_colors.append(self.hex2rgb("CFFFB0"))
            channel_colors.append(self.hex2rgb("5998CF"))
            self.channel_controls.append(channel_vertical_control_group(0, 'Channel A', self.range_names, channel_colors[0]))
            self.channel_controls.append(channel_vertical_control_group(1, 'Channel B', self.range_names, channel_colors[1]))
            self.channel_controls.append(channel_vertical_control_group(2, 'Channel C', self.range_names, channel_colors[2]))
            self.channel_controls.append(channel_vertical_control_group(3, 'Channel D', self.range_names, channel_colors[3]))
            for cc in self.channel_controls:
                self.control_col2.addWidget(cc.control_group)
                cc.enable_button.checkStateChanged.connect(
                    lambda state, idx = cc.idx : self.enable_checkbox_changed(idx))
                cc.voltage_scale_selector.textActivated.connect(
                    lambda text, idx = cc.idx : self.activate_channel(idx, True))
                if cc.idx == 0:
                    cc.voltage_scale_selector.setCurrentIndex(9)
                cc.logging_button.checkStateChanged.connect(
                    cc.update_save_data)
                cc.display_button.checkStateChanged.connect(
                    lambda text, idx = cc.idx : self.reset_traces(idx))
            self.control_col2.addStretch(1)
            self.channel_controls[0].enable_button.setChecked(True)
            self.channel_controls[0].display_button.setChecked(True)
            self.enable_checkbox_changed(0)
            self.timebase_scales = []
            for oom in list(range(-8, 0)):
                for prefix in [1, 2, 5]:
                    self.timebase_scales.append(prefix * 10**oom)
            timebase_scale_names = [si_format(ts) + 's' for ts in self.timebase_scales]
            self.timebase_scale_selector.addItems(timebase_scale_names)
            self.timebase_scale_selector.setCurrentIndex(10)
            self.timebase_scale_selector.textActivated.connect(self.init_timebase)

            self.ps_server.set_scope_resolution(8)
            self.init_timebase()

            self.osci_state_label.setText("Connected")
            self.connect_button.setText("Disconnect")
            self.connected = True

            self.run_button.setChecked(False)

            self.draw_hline()
        else:
            print("Shutting down picoscope connection")
            self.ps_server.stop_loop()
            self.osci_state_label.setText("Not Connected")
            self.connect_button.setText("Connect")
            self.connected = False

    def reset_traces(self, idx):
        if self.channel_controls[idx].enable_button.isChecked() or idx == -1:
            new_traces = []
            for cc in self.channel_controls:
                if cc.display_button.isChecked():
                    color = cc.color
                    new_traces.append(Trace(self.plot_widget, cc.idx, cc.name, [0, 0], [0, 0], color, {}))
            for new_trace in new_traces:
                for old_trace in self.traces:
                    if new_trace.idx == old_trace.idx:
                        new_trace.x = old_trace.x
                        new_trace.y = old_trace.y
            for trace in self.traces:
                trace.delete()
            self.traces = new_traces
            self.update_plot()
        else:
            self.channel_controls[idx].display_button.setChecked(False)

    def update_plot(self):
        if self.connected:
            if self.running:
                if self.ps_server.new_waveform_available():
                    # Import to grab the tag before the waveform, before the next tag is already sent in by the ARTIQ
                    # A better system for this is mandatory on the long term
                    self.tag_state, self.waveform_tag = self.ps_server.send_tag()
                    print(tagging_enum(self.tag_state), self.waveform_tag)
                    if self.tag_state == tagging_enum.WAVEFORM_TAGGED.value:
                        encoded_waveform = self.ps_server.send_latest_waveform()
                        self.tag_display.update(self.tag_state, self.waveform_tag)
                        if not encoded_waveform == b'NONE':
                            # try:
                            waveform = decode_bytes_to_numpy(encoded_waveform)
                            plot_idcs = [trace.idx for trace in self.traces]
                            for idx, trace in zip(range(len(self.traces)), self.traces):
                                if plot_idcs[idx] + 1 >= len(waveform):
                                    print(plot_idcs)
                                trace.set_averaging(self.averages)
                                scale_idx = self.channel_controls[trace.idx].voltage_scale_selector.currentIndex()
                                scale_text = self.range_names[scale_idx][3:-2]
                                scale = si_parse(scale_text)
                                offset = scale \
                                    * float(self.channel_controls[trace.idx].offset_selector.value()) \
                                    / 5
                                y = offset + waveform[plot_idcs[idx] + 1]
                                if self.equiscale_button.isChecked():
                                    y = y / scale
                                trace.add_waveform(x = waveform[0], y = y)
                                trace.plot()

                            # self.text_label = pg.LabelItem("%.8g" % self.tag_display.sweep_param)
                            # self.text_label.setParentItem(self.plot_widget.graphicsItem())
                            # self.text_label.anchor(itemPos=(0.025, 0.025), parentPos=(0.025, 0.025))

                            integral_idx = self.integral_source.currentIndex()
                            if self.channel_controls[integral_idx].enable_button.isChecked():
                                enabled_channels = []
                                for cc, idx in zip(self.channel_controls, range(len(self.channel_controls))):
                                    if cc.idx == integral_idx:
                                        integral_idx = idx
                                self.x = waveform[0]
                                self.y = waveform[integral_idx + 1]

                                self.integrate_curve(send_integral = True)
                            else:
                                self.integral_value.setText("Chosen integral channel invalid")

                            if self.equiscale_button.isChecked():
                                self.plot_widget.setRange(yRange = [-1, 1])

                            # except Exception as e:
                            #     print(e)
                                # print(encoded_waveform)
                                # print(waveform)


    def timebase_sampling_rate_12bit(self, n):
        if n < 1 or n > (2**32 - 2):
            raise Exception("Invalid timebase input")
        elif n < 3:
            return (2**(n-1)) / 1e+9
        else:
            return (n - 3) / 62.5e+6

    def timebase_sampling_rate_8bit(self, n):
        if n < 0 or n > (2**32 - 2):
            raise Exception("Invalid timebase input")
        elif n < 3:
            return (2**n) / 1e+9
        else:
            return (n - 2) / 125.0e+6

    def init_timebase(self):
        self.n_samples = self.samples_selector.value();
        t_per_div = self.timebase_scales[self.timebase_scale_selector.currentIndex()]
        total_time = t_per_div * 10
        sample_interval = total_time / self.n_samples
        for n in range(3, 2**32 - 1):
            # TODO: fix later
            if self.timebase_sampling_rate_8bit(n) > sample_interval:
                break
        self.timebase = n - 1
        print("timebase: ", self.timebase)
        self.ps_server.set_timebase(round(self.timebase), round(self.n_samples))
        holdoff_samples = self.calculate_holdoff()
        self.ps_server.set_pre_trigger_samples(self.pre_trigger_samples)
        self.ps_server.set_trigger(
             self.trigger_control_group.trig_channel_selector.currentIndex(),
             self.trigger_level,
             self.trigger_control_group.trig_mode.currentText(),
             int(holdoff_samples)
            )

    def enable_checkbox_changed(self, channel_idx):
        print("Checkbox changed channel", channel_idx, self.channel_controls[channel_idx].enable_button.isChecked())
        self.activate_channel(
            channel_idx,
            self.channel_controls[channel_idx].enable_button.isChecked()
            )

    def activate_channel(self, channel_idx, activate):
        print("activate channel", channel_idx, activate)
        if activate:
            self.ps_server.set_active_channel(
                channel_idx,
                self.channel_controls[channel_idx].voltage_scale_selector.currentIndex(),
                'DC'
                )
            print(f"Channel {channel_idx} enabled.  Voltage scale", self.channel_controls[channel_idx].voltage_scale_selector.currentIndex())
        else:
            self.ps_server.deactivate_channel(channel_idx)
            print(f"Channel {channel_idx} disabled.")
        self.draw_hline()

    def reset_rois(self):
        n_rois = 0
        current_n_rois = len(self.rois)
        self.integral_tab.reset_traces()
        
        step = (self.x[-1] - self.x[0]) / (n_rois + 1)
        
        # Add new ROIs if increasing the number
        if n_rois > current_n_rois:
            for i in range(current_n_rois, n_rois):
                start = step * (i + 1) - step / 2
                end = start + step / 2

                # Cycle through colors for shading
                roi_color = self.colors[i % len(self.colors)]
                
                # Create new LinearRegionItem with shading
                roi = pg.LinearRegionItem(
                    [start, end], 
                    movable=True, 
                    pen=pg.mkPen(roi_color[:3]),  # Use RGB for pen color
                    brush=pg.mkBrush(roi_color)   # Use RGBA for brush color
                )

                roi.sigRegionChanged.connect(self.integrate_curve)

                # Add new ROI to the plot and the list
                self.plot_widget.addItem(roi)
                self.rois.append(roi)
        # Remove extra ROIs if reducing the number
        elif n_rois < current_n_rois:
            for i in range(n_rois, current_n_rois):
                self.plot_widget.removeItem(self.rois[i])
            self.rois = self.rois[:n_rois]
        self.update_rois()

    def update_rois(self):
        # Get the current number of ROIs from the spin box
        n_rois = self.n_ROIs.value()
        self.integral_tab.init_traces(n_rois)

        # Number of current ROIs
        current_n_rois = len(self.rois)
        
        step = (self.x[-1] - self.x[0]) / (n_rois + 1)
        
        # Add new ROIs if increasing the number
        if n_rois > current_n_rois:
            for i in range(current_n_rois, n_rois):
                start = step * (i + 1) - step / 2
                end = start + step / 2

                # Cycle through colors for shading
                roi_color = self.colors[i % len(self.colors)]
                
                # Create new LinearRegionItem with shading
                roi = pg.LinearRegionItem(
                    [start, end], 
                    movable=True, 
                    pen=pg.mkPen(roi_color[:3]),  # Use RGB for pen color
                    brush=pg.mkBrush(roi_color)   # Use RGBA for brush color
                )

                roi.sigRegionChanged.connect(self.integrate_curve)

                # Add new ROI to the plot and the list
                self.plot_widget.addItem(roi)
                self.rois.append(roi)

        # Remove extra ROIs if reducing the number
        elif n_rois < current_n_rois:
            for i in range(n_rois, current_n_rois):
                self.plot_widget.removeItem(self.rois[i])
            self.rois = self.rois[:n_rois]

        # Apply locking state to ROIs based on the checkbox state
        self.toggle_lock_rois()
        self.integrate_curve()

    def toggle_lock_rois(self):
        """Lock or unlock the ROIs based on the state of the checkbox."""
        lock = self.lock_checkbox.isChecked()
        for roi in self.rois:
            roi.setMovable(not lock)  # Set ROIs movable or immovable depending on checkbox state
        self.n_ROIs.setEnabled(not lock)

    def integrate_curve(self, send_integral = False):
        # Loop over each ROI and calculate the integral within that region
        integrals = ""
        first = True
        for idx, roi, color in zip(range(len(self.rois)), self.rois, self.color_names):
            region = roi.getRegion()
            if region[0] > self.x[0] and region[1] < self.x[-1]:
                idx_min = np.searchsorted(self.x, region[0])
                idx_max = np.searchsorted(self.x, region[1])
                x_region = self.x[idx_min:idx_max]
                y_region = self.y[idx_min:idx_max]

                integral = simpson(y_region, x = x_region)
                if self.normalization_button.isChecked():
                    integral = integral / abs(region[1] - region[0])
                if self.force_background_ROI.isChecked() and idx == 0:
                    background_integral = integral
                    self.integral_tab.traces[0].show = False
                else:
                    background_integral = 0.0
                    self.integral_tab.traces[0].show = True
                integral -= background_integral

                if first:
                    first = False
                else:
                    integrals += ",  "
                integrals += f"{color}: {integral:6.4g}"

                if send_integral:
                    if self.tag_state == tagging_enum.WAVEFORM_TAGGED.value:
                        self.integral_tab.traces[idx].add_ypoint(integral, nx = self.tag_display.sweep_param)
                    else:
                        self.integral_tab.traces[idx].add_ypoint(integral, nx = self.integral_tab.cum_idx + 1)
            else:
                integrals = "INVALID"
                break
        
        self.integral_value.setText(integrals)
        if send_integral:
            self.integral_tab.update()

    def draw_hline(self):
        if self.connected and not self.running:
            tc = self.trigger_control_group.trig_channel_selector.currentIndex()
            tc_scale_idx = self.channel_controls[tc].voltage_scale_selector.currentIndex()
            tc_scale_text = self.range_names[tc_scale_idx][3:-2]
            tc_scale = si_parse(tc_scale_text)
            self.trigger_level = tc_scale * float(self.trigger_control_group.slider.sliderPosition()) / 512.0
            self.trigger_control_group.trigger_level_readout_label.setText("%sV" % si_format(self.trigger_level))
            
            if self.trigger_control_group.draw_button.isChecked():
                # Trigger drawing
                self.trigger_line.setVisible(True)
                if self.equiscale_button.isChecked():
                    self.trigger_line.setValue(self.trigger_level / tc_scale)
                else:
                    self.trigger_line.setValue(self.trigger_level)
        else:
            self.trigger_line.setVisible(False)

class channel_vertical_control_group():
    def __init__(self, idx, channel_name, vertical_scales, color):
        self.idx = idx
        self.save_data = False
        self.display   = False
        self.name = channel_name
        self.color = color

        self.control_group = QGroupBox(channel_name)
        self.control_group.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.layout = QVBoxLayout()

        self.layout.addWidget(QLabel("Vertical Scale"))
        self.voltage_scale_selector = QComboBox()
        self.voltage_scale_selector.addItems(vertical_scales)
        self.layout.addWidget(self.voltage_scale_selector)

        self.layout.addWidget(QLabel("Vertical Offset"))
        self.offset_selector = SingleClickDial()
        self.offset_selector.setRange(-5, 5)  # Trigger range
        self.offset_selector.setValue(0)
        self.offset_selector.setNotchesVisible(True)
        self.layout.addWidget(self.offset_selector)

        self.enable_row = QHBoxLayout()
        self.enable_row.addWidget(QLabel("enable"))
        self.enable_row.addStretch(1)
        self.enable_button = QCheckBox()
        self.enable_row.addWidget(self.enable_button)
        self.layout.addLayout(self.enable_row)

        self.logging_row = QHBoxLayout()
        self.logging_row.addWidget(QLabel("save data"))
        self.logging_row.addStretch(1)
        self.logging_button = QCheckBox()
        self.logging_row.addWidget(self.logging_button)
        self.layout.addLayout(self.logging_row)

        self.display_row = QHBoxLayout()
        self.display_row.addWidget(QLabel("show trace"))
        self.display_row.addStretch(1)
        self.display_button = QCheckBox()
        self.display_row.addWidget(self.display_button)
        self.layout.addLayout(self.display_row)

        self.layout.addWidget(ColorBoxWidget(
            self.color[0], self.color[1], self.color[2]))

        self.control_group.setLayout(self.layout)

    def update_save_data(self):
        self.save_data = self.logging_button.isChecked()
        print(f"Channel {self.idx}: Logging {self.save_data}")

    def update_display(self):
        self.display = self.display_button.isChecked()
        print(f"Channel {self.idx}: Display {self.display}")

class trigger_control_group():
    def __init__(self, draw_hline):
        self.control_group = QGroupBox("Trigger Control")
        self.control_group.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.layout = QVBoxLayout()

        self.layout.addWidget(QLabel("Trigger Channel"))
        self.trig_channel_selector = QComboBox()
        self.trig_channel_selector.addItems(['A', 'B', 'C', 'D'])
        self.layout.addWidget(self.trig_channel_selector)

        self.layout.addWidget(QLabel("Trigger Mode"))
        self.trig_mode = QComboBox()
        self.trig_mode.addItems(['RISING', 'FALLING'])
        self.layout.addWidget(self.trig_mode)

        # Create the vertical slider
        self.layout.addWidget(QLabel("Trigger Level"))
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setFixedWidth(125)
        self.slider.setMinimum(-512)
        self.slider.setMaximum( 512)
        self.slider.setValue(64)
        self.slider.valueChanged.connect(draw_hline)
        self.layout.addWidget(self.slider, alignment=Qt.AlignCenter)

        # Trigger level readout
        self.tl_readout_row = QHBoxLayout()
        self.tl_readout_row.addWidget(QLabel("Trig. Lev. "))
        self.tl_readout_row.addStretch(1)
        self.trigger_level_readout_label = QLabel("0.0")
        self.tl_readout_row.addWidget(self.trigger_level_readout_label)
        self.layout.addLayout(self.tl_readout_row)

        # Draw trigger?
        self.draw_row = QHBoxLayout()
        self.draw_row.addWidget(QLabel("draw trigger"))
        self.draw_row.addStretch(1)
        self.draw_button = QCheckBox()
        self.draw_row.addWidget(self.draw_button)
        self.layout.addLayout(self.draw_row)

        self.control_group.setLayout(self.layout)


class Trace():
    def __init__(self, plot_widget, idx: int, name: str, x: list, y: list, color: tuple, metadata_dict: dict = {}):
        self.idx = idx
        self.name = name
        self.plot_widget = plot_widget
        self.x = [float(z) for z in x]
        self.y = [float(z) for z in y]
        self.metadata_dict = metadata_dict
        self.pen = pg.mkPen(color = color)
        self.trace = self.plot_widget.plot(self.x, self.y, name = self.name, pen = self.pen)
        self.averaging = 1
        self.reset = False
        self.by = np.zeros(len(self.y))
        self.show = True
        self.scatter = False

    def delete(self):
        self.plot_widget.removeItem(self.trace)


    def add_ypoint(self, ny: float, nx = None):
        self.x = list(self.x)
        self.y = list(self.y)
        if nx is None:
            print('Tag x')
            self.x.append(len(self.x) + 1)
        else:
            self.x.append(nx)
        self.y.append(ny)

    def set_averaging(self, n: int):
        if self.averaging != n:
            print("Updating averages", n)
            self.averaging = n
            self.reset = True

    def setData(self, x, y):
        self.x = x
        self.y = np.array(y)
        if len(y) != len(self.by):
            self.by = np.zeros(len(y))

    def add_waveform(self, x, y):
        if self.reset:
            self.setData(x, y)
            self.reset = False
        else:
            # Heuristic to make sure we're on the same x scale
            if len(self.x) == len(x) and (x[0] == self.x[0] and x[-1] == self.x[-1]):
                # Remove background for averaging
                if len(y) == len(self.by):
                    self.y = np.array(self.y) + np.array(self.by)
                # If y = 0 for all, we know that this is the first waveform
                if not np.sum(np.abs(self.y)) == 0:
                    self.y = self.y - (self.y / float(self.averaging))
                    self.y = self.y + (     y / float(self.averaging))
                self.setData(x, self.y)
                # Remove background
                if len(y) == len(self.by):
                    self.y = np.array(self.y) - np.array(self.by)
            else:
                self.reset = False
                if len(y) == len(self.by):
                    self.setData(x, np.array(y) - np.array(self.by))
                else:
                    self.setData(x, y)

    def reset_average(self):
        self.y = np.zeros(len(self.y))

    def add_metadata(self, field: str, info: str):
        metadata_dict[field] = info

    def plot(self):
        if self.show:
            if len(self.x) == len(self.y) and len(self.x) > 0:
                self.trace.setData(x = self.x, y = self.y)
            self.trace.setVisible(True)
        else:
            self.trace.setVisible(False)

    def set_background(self):
        self.by = self.y

    def delete_background(self):
        self.by = np.zeros(len(self.y))


class IntegralTab():
    def __init__(self, TabWidget):
        self.TabWidget = TabWidget

        self.traces = []

        self.plot_widget = pg.PlotWidget()

        # Label
        self.toplabel = QLabel("Integral View")
        init_widget(self.toplabel, "", "TODO More Info")

        # Timebase control section
        self.timebase_scale_selector = QComboBox()
        self.timebase_scale_selector.addItems(["a", "b"])
        self.timebase_delay_selector = SingleClickDial()
        self.timebase_delay_selector.setRange(-5, 5)
        self.timebase_delay_selector.setValue(0)
        self.timebase_delay_selector.setNotchesVisible(True)

        # Layouts
        self.top_layout = QVBoxLayout()
        self.top_layout.addWidget(self.toplabel)
        self.plot_layer = QHBoxLayout()
        self.control_layer = QHBoxLayout()
        self.control_layer.addStretch(1)
        self.reset_button = QPushButton("Reset")
        self.reset_button.clicked.connect(self.reset_traces)
        self.control_layer.addWidget(self.reset_button)
        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self.save_data)
        self.control_layer.addWidget(self.save_button)
        self.plot_layer.addWidget(self.plot_widget)
        self.top_layout.addLayout(self.plot_layer)
        self.top_layout.addLayout(self.control_layer)

        # Add the container widget to the TabWidget instead of the layout directly
        self.container_widget = QWidget()
        self.container_widget.setLayout(self.top_layout)
        self.TabWidget.layout().addWidget(self.container_widget)

        # Cumulative x index
        self.cum_idx = 0

    def reset_traces(self):
        for trace in self.traces:
            trace.setData([], [])
        self.plot()

    def init_traces(self, N_traces):
        self.N_traces = N_traces
        for trace in self.traces:
            trace.delete()
        self.traces = [Trace(self.plot_widget, idx, 'ROI' + str(idx), [], [], colors[idx][0:3], {}) for idx in range(self.N_traces)]
        for trace in self.traces:
            trace.scatter = True
        self.plot()

    def update(self):
        idcs = [trace.idx for trace in self.traces]
        self.cum_idx = max(idcs)
        self.plot()

    def plot(self):
        maxy = 0
        miny = 0
        for trace in self.traces:
            trace.plot()
            if len(trace.y) > 0:
                maxy = max([maxy, max(trace.y)])
                miny = min([maxy, min(trace.y)])
        self.plot_widget.setRange(yRange = [miny, maxy])

    def save_data(self):
        for trace in self.traces:
            np.savetxt(f"s{trace.idx}.csv", np.vstack([trace.x, trace.y]).T, delimiter=",")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # Start labrad connection
        self.init_labrad()

        # Set the window title
        self.setWindowTitle("Data Live Plot GUI")

        # Create the central widget
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        # Create the main layout
        self.main_layout = QHBoxLayout()

        # Add the SideTabWidget to the main layout
        self.tabs = SideTabWidget()
        self.main_layout.addWidget(self.tabs)

        # Set the layout to the central widget
        self.central_widget.setLayout(self.main_layout)

        # Put together the integral view tab
        self.integral_tab = IntegralTab(self.tabs.tab2_layout)

        # Put together the oscilloscope tab
        self.oscope_tab = OscilloscopeTab(self.tabs.tab1_layout, self.cxn, self.integral_tab)

        # Put together the settings tab
        self.settings_tab = SettingsTab(self.tabs.tab3_layout)

        # Update loop for live plotting
        self.init_update_plot_timer()

    def init_labrad(self):
        self.cxn = labrad.connect('192.168.5.6', name = '', password = '')

    def init_update_plot_timer(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.oscope_tab.update_plot)
        self.timer.start(2)

    def closeEvent(self, event):
        if self.oscope_tab.connected:
            self.oscope_tab.ps_server.stop_loop()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Create and show the main window
    window = MainWindow()
    # window.show()
    window.showMaximized()

    # Execute the application
    sys.exit(app.exec())