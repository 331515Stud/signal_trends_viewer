from PyQt6.QtWidgets import QDialog, QCalendarWidget, QSpinBox, QDialogButtonBox, QVBoxLayout, QFormLayout, QHBoxLayout, QLabel, QMessageBox, QSizePolicy
from PyQt6.QtCore import QDateTime, QDate, QTime

class DateTimeSelectionDialog(QDialog):
    def __init__(self, initial_datetime=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Выбор даты и времени начала")
        self.setMinimumSize(350, 300)

        self.calendar = QCalendarWidget(self)
        self.calendar.setGridVisible(True)
        self.calendar.setMaximumDate(QDate.currentDate())
        if initial_datetime:
            self.calendar.setSelectedDate(QDate.fromString(initial_datetime.strftime("%Y-%m-%d"), "yyyy-MM-dd"))

        self.hour_spin = QSpinBox(self)
        self.hour_spin.setRange(0, 23)
        self.hour_spin.setValue(initial_datetime.hour if initial_datetime else QTime.currentTime().hour())
        self.hour_spin.setFixedWidth(60)
        self.hour_spin.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self.minute_spin = QSpinBox(self)
        self.minute_spin.setRange(0, 59)
        self.minute_spin.setValue(initial_datetime.minute if initial_datetime else QTime.currentTime().minute())
        self.minute_spin.setFixedWidth(60)
        self.minute_spin.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self.second_spin = QSpinBox(self)
        self.second_spin.setRange(0, 59)
        self.second_spin.setValue(initial_datetime.second if initial_datetime else QTime.currentTime().second())
        self.second_spin.setFixedWidth(60)
        self.second_spin.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        buttons = QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        self.button_box = QDialogButtonBox(buttons)
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setText("Принять")
        self.button_box.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")

        main_layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        form_layout.addRow("Выберите дату:", self.calendar)

        time_layout = QHBoxLayout()
        time_layout.setSpacing(2)
        time_layout.setContentsMargins(0, 0, 0, 0)
        time_layout.addWidget(self.hour_spin)
        colon_label1 = QLabel(":")
        colon_label1.setFixedWidth(10)
        time_layout.addWidget(colon_label1)
        time_layout.addWidget(self.minute_spin)
        colon_label2 = QLabel(":")
        colon_label2.setFixedWidth(10)
        time_layout.addWidget(colon_label2)
        time_layout.addWidget(self.second_spin)
        form_layout.addRow("Выберите время:", time_layout)

        main_layout.addLayout(form_layout)
        main_layout.addWidget(self.button_box)

        self.button_box.accepted.connect(self.validate_and_accept)
        self.button_box.rejected.connect(self.reject)

    def validate_and_accept(self):
        selected_date = self.calendar.selectedDate()
        selected_time = QTime(self.hour_spin.value(), self.minute_spin.value(), self.second_spin.value())
        selected_datetime = QDateTime(selected_date, selected_time)
        current_datetime = QDateTime.currentDateTime()

        if selected_datetime > current_datetime:
            QMessageBox.warning(
                self,
                "Ошибка валидации",
                "Выбранная дата и время не могут быть в будущем.\n"
                "Пожалуйста, выберите корректную дату."
            )
            return

        self.accept()

    def get_selected_datetime(self):
        selected_date = self.calendar.selectedDate()
        selected_time = QTime(self.hour_spin.value(), self.minute_spin.value(), self.second_spin.value())
        return QDateTime(selected_date, selected_time)