# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'kingai\\core\\qt.py'
# Bytecode version: 3.10.b1 (3439)
# Source timestamp: 1970-01-01 00:00:00 UTC (0)

"""\nqt.py\n=====\nTitik impor Qt TUNGGAL untuk seluruh package `kingai` - modul lain mengimpor\nkelas Qt dari sini, bukan langsung dari PySide2. Kalau binding Qt suatu saat\ndiganti (mis. PySide6), cukup file ini yang diubah.\n\nPySide2 (Qt 5.15) dipilih karena mendukung Windows 7 s/d 11 sekaligus,\nsama seperti QueenAI.\n"""
try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:
    try:
        from PySide2 import QtCore, QtGui, QtWidgets
    except ImportError as exc:
        raise RuntimeError('Vilona AI requires PySide6 or PySide2 to be installed.') from exc
Qt = QtCore.Qt
Signal = QtCore.Signal
Property = QtCore.Property
QObject = QtCore.QObject
QCoreApplication = QtCore.QCoreApplication
QProcess = QtCore.QProcess
QProcessEnvironment = QtCore.QProcessEnvironment
QEventLoop = QtCore.QEventLoop
QTimer = QtCore.QTimer
QElapsedTimer = QtCore.QElapsedTimer
QPoint = QtCore.QPoint
QPointF = QtCore.QPointF
QSize = QtCore.QSize
QRect = QtCore.QRect
QRectF = QtCore.QRectF
QEvent = QtCore.QEvent
QUrl = QtCore.QUrl
QDate = QtCore.QDate
QPropertyAnimation = QtCore.QPropertyAnimation
QVariantAnimation = QtCore.QVariantAnimation
QEasingCurve = QtCore.QEasingCurve
QSortFilterProxyModel = QtCore.QSortFilterProxyModel
QRegExp = getattr(QtCore, 'QRegularExpression', getattr(QtCore, 'QRegExp', None))
QIcon = QtGui.QIcon
QColor = QtGui.QColor
QFont = QtGui.QFont
QFontMetrics = QtGui.QFontMetrics
QFontMetricsF = QtGui.QFontMetricsF
QBrush = QtGui.QBrush
QLinearGradient = QtGui.QLinearGradient
QRadialGradient = QtGui.QRadialGradient
QConicalGradient = QtGui.QConicalGradient
QPainter = QtGui.QPainter
QPainterPath = QtGui.QPainterPath
QPen = QtGui.QPen
QPixmap = QtGui.QPixmap
QImage = QtGui.QImage
QPolygonF = QtGui.QPolygonF
QRegion = QtGui.QRegion
QTransform = QtGui.QTransform
QCursor = QtGui.QCursor
QDesktopServices = QtGui.QDesktopServices
QTextCursor = QtGui.QTextCursor
QStandardItemModel = QtGui.QStandardItemModel
QStandardItem = QtGui.QStandardItem
QKeySequence = QtGui.QKeySequence
if hasattr(QtGui, 'QRegularExpressionValidator'):
    QRegExpValidator = QtGui.QRegularExpressionValidator
elif hasattr(QtGui, 'QRegExpValidator'):
    QRegExpValidator = QtGui.QRegExpValidator
else:
    QRegExpValidator = None
QApplication = QtWidgets.QApplication
QWidget = QtWidgets.QWidget
QDialog = QtWidgets.QDialog
QFrame = QtWidgets.QFrame
QVBoxLayout = QtWidgets.QVBoxLayout
QHBoxLayout = QtWidgets.QHBoxLayout
QGridLayout = QtWidgets.QGridLayout
QBoxLayout = QtWidgets.QBoxLayout
QSpacerItem = QtWidgets.QSpacerItem
QStackedWidget = QtWidgets.QStackedWidget
QSizePolicy = QtWidgets.QSizePolicy
QLabel = QtWidgets.QLabel
QLineEdit = QtWidgets.QLineEdit
QTextBrowser = QtWidgets.QTextBrowser
QPushButton = QtWidgets.QPushButton
QAbstractButton = QtWidgets.QAbstractButton
QToolButton = QtWidgets.QToolButton
QComboBox = QtWidgets.QComboBox
QCheckBox = QtWidgets.QCheckBox
QSpinBox = QtWidgets.QSpinBox
QDoubleSpinBox = QtWidgets.QDoubleSpinBox
QDateEdit = QtWidgets.QDateEdit
QCalendarWidget = QtWidgets.QCalendarWidget
QScrollArea = QtWidgets.QScrollArea
QListWidget = QtWidgets.QListWidget
QListWidgetItem = QtWidgets.QListWidgetItem
QCompleter = QtWidgets.QCompleter
QMessageBox = QtWidgets.QMessageBox
QFileDialog = QtWidgets.QFileDialog
QGraphicsOpacityEffect = QtWidgets.QGraphicsOpacityEffect
QShortcut = getattr(QtWidgets, 'QShortcut', QtGui.QShortcut)
QMenu = QtWidgets.QMenu
def qapp_exec(app) -> int:
    """PySide2/Qt5 memakai `exec_()`, sementara Qt6 memakai `exec()`."""
    exec_func = getattr(app, 'exec', None)
    if exec_func is not None:
        return exec_func()
    return app.exec_()
def start_system_resize(window_handle, edges) -> bool:
    """`QWindow.startSystemResize` (Qt 5.15) - fallback False kalau tidak ada."""
    func = getattr(window_handle, 'startSystemResize', None)
    if func is None:
        return False
    else:
        func(edges)
        return True