from PyQt6.QtGui import QPalette, QColor
from PyQt6.QtCore import Qt
from event_bus import EventBus


class ThemeManager:
    THEMES = {
        'dark': {
            'Window': QColor(53, 53, 53),
            'WindowText': Qt.GlobalColor.white,
            'Base': QColor(35, 35, 35),
            'AlternateBase': QColor(53, 53, 53),
            'ToolTipBase': QColor(25, 25, 25),
            'ToolTipText': Qt.GlobalColor.white,
            'Text': Qt.GlobalColor.white,
            'Button': QColor(53, 53, 53),
            'ButtonText': Qt.GlobalColor.white,
            'BrightText': Qt.GlobalColor.red,
            'Link': QColor(42, 130, 218),
            'Highlight': QColor(42, 130, 218),
            'HighlightedText': Qt.GlobalColor.black,
        },
        'light': {
            'Window': QColor(240, 240, 240),
            'WindowText': Qt.GlobalColor.black,
            'Base': QColor(255, 255, 255),
            'AlternateBase': QColor(240, 240, 240),
            'ToolTipBase': QColor(255, 255, 255),
            'ToolTipText': Qt.GlobalColor.black,
            'Text': Qt.GlobalColor.black,
            'Button': QColor(240, 240, 240),
            'ButtonText': Qt.GlobalColor.black,
            'BrightText': Qt.GlobalColor.red,
            'Link': QColor(0, 0, 255),
            'Highlight': QColor(76, 163, 224),
            'HighlightedText': Qt.GlobalColor.white,
        }
    }

    def __init__(self, bus: EventBus):
        self.bus = bus
        self.current_theme = 'dark'



    @classmethod
    def get_palette(cls, theme_name):
        palette = QPalette()
        theme = cls.THEMES.get(theme_name, cls.THEMES['dark'])
        for role_name, color in theme.items():
            role = getattr(QPalette.ColorRole, role_name)
            palette.setColor(role, color)
        return palette

    @classmethod
    def get_button_style(cls, theme_name):
        is_dark = theme_name == 'dark'
        bg_color = "#353535" if is_dark else "#f0f0f0"
        text_color = "white" if is_dark else "black"
        border_color = "#ffffff" if is_dark else "#cccccc"
        hover_color = "#444444" if is_dark else "#e0e0e0"
        pressed_color = "#464646" if is_dark else "#d0d0d0"

        return f"""
            QToolButton {{
                background-color: {bg_color};
                color: {text_color};
                font-weight: bold;
                border: 2px solid {border_color};
                border-radius: 8px;
                padding: 5px;
            }}
            QToolButton:hover {{
                background-color: {hover_color};
            }}
            QToolButton:pressed {{
                background-color: {pressed_color};
            }}
        """
    @classmethod
    def get_line_edit_style(cls, theme_name):
        is_dark = theme_name == 'dark'
        bg_color = "#404040" if is_dark else "white"
        text_color = "white" if is_dark else "black"
        border_color = "#555555" if is_dark else "#cccccc"
        focus_color = "#2a82da" if is_dark else "#4c9eff"

        return f"""
            QLineEdit {{
                background-color: {bg_color};
                color: {text_color};
                border: 2px solid {border_color};
                border-radius: 4px;
                padding: 5px;
            }}
            QLineEdit:focus {{
                border-color: {focus_color};
            }}
        """

    @classmethod
    def get_label_style(cls, theme_name):
        is_dark = theme_name == 'dark'
        bg_color = "#404040" if is_dark else "#e0e0e0"
        text_color = "white" if is_dark else "black"
        border_color = "#555555" if is_dark else "#cccccc"

        return f"""
            QLabel {{
                background-color: {bg_color};
                color: {text_color};
                border: 1px solid {border_color};
                border-radius: 3px;
                padding: 3px;
            }}
        """

    @classmethod
    def get_checkbox_style(cls, theme_name):
        is_dark = theme_name == 'dark'
        bg_color = "#404040" if is_dark else "white"
        text_color = "white" if is_dark else "black"
        border_color = "#555555" if is_dark else "#cccccc"
        highlight_color = "#2a82da" if is_dark else "#4c9eff"

        return f"""
            QCheckBox {{
                color: {text_color};
                spacing: 5px;
            }}
            QCheckBox::indicator {{
                width: 13px;
                height: 13px;
            }}
            QCheckBox::indicator:unchecked {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 3px;
            }}
            QCheckBox::indicator:checked {{
                background-color: {highlight_color};
                border: 1px solid {highlight_color};
                border-radius: 3px;
            }}
        """

    @classmethod
    def get_slider_style(cls, theme_name):
        is_dark = theme_name == 'dark'
        bg_color = "#404040" if is_dark else "white"
        text_color = "white" if is_dark else "black"
        border_color = "#555555" if is_dark else "#cccccc"

        return f"""
            QSlider::groove:horizontal {{
                border: 1px solid {border_color};
                height: 8px;
                background: {bg_color};
                margin: 2px 0;
                border-radius: 4px;
            }}
            QSlider::handle:horizontal {{
                background: {text_color};
                border: 1px solid {border_color};
                width: 18px;
                margin: -2px 0;
                border-radius: 3px;
            }}
        """

    @classmethod
    def get_toolbar_style(cls, theme_name):
        is_dark = theme_name == 'dark'
        bg_color = "#353535" if is_dark else "#f0f0f0"
        border_color = "#555555" if is_dark else "#cccccc"
        text_color = "white" if is_dark else "black"
        highlight_color = "#2a82da" if is_dark else "#4c9eff"

        return f"""
            QToolBar {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 5px;
                padding: 5px;
                spacing: 5px;
                color: {text_color};
            }}
            QToolBar::separator {{
                width: 1px;
                background-color: {border_color};
                margin-left: 5px;
                margin-right: 5px;
            }}
            QToolBar::item {{
                margin: 2px;
                padding: 5px;
            }}
        """