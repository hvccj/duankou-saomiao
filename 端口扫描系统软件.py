import sys
import socket
import threading
import time
import platform
from queue import Queue, Empty

from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QHBoxLayout,
    QMessageBox, QHeaderView, QFileDialog, QProgressBar,
    QCheckBox, QAbstractItemView, QTextEdit
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, pyqtSlot

def get_precise_windows_version():
    if platform.system() != "Windows":
        return platform.system(), platform.release(), platform.version()
    version = sys.getwindowsversion()
    major, build = version.major, version.build
    if major == 10 and build >= 22000:
        return "Windows 11", f"{major}", f"Build {build}"
    elif major == 10:
        return "Windows 10", f"{major}", f"Build {build}"
    else:
        return f"Windows {major}", f"{major}", f"Build {build}"

def get_local_ip():
    """Return the local IPv4 address, falling back to loopback on failure."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'

def get_os_details():
    try:
        sysname, release, build = get_precise_windows_version()
        sysinfo = [
            f"系统: {sysname} {release} {build}",
            f"平台: {platform.platform()}",
            f"内核: {platform.version()}",
            f"架构: {platform.machine()}",
            f"Python: {platform.python_version()}"
        ]
        return '\n'.join(sysinfo)
    except Exception:
        return "未知操作系统"

def get_hostname():
    try:
        return socket.gethostname()
    except Exception:
        return "未知主机名"

def get_service_name(port):
    try:
        return socket.getservbyport(port)
    except Exception:
        return "未知服务"

class PortScannerThread(QThread):
    """Run port probes in bounded worker threads and emit scan updates."""

    progress = pyqtSignal(int)
    result = pyqtSignal(int, str, float, str)
    finish = pyqtSignal()

    def __init__(self, ip, ports, fast_mode, threads, parent=None):
        super().__init__(parent)
        self.ip = ip
        self.ports = ports
        self.fast_mode = fast_mode
        self.threads = threads
        self.running = True

    def scan_worker(self, task_queue):
        """Process queued ports until the queue is empty or scanning stops."""
        while self.running:
            try:
                port = task_queue.get_nowait()
            except Empty:
                return
            except Exception:
                return
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                sock.settimeout(0.075 if self.fast_mode else 0.22)
                start = time.time()
                res = sock.connect_ex((self.ip, port))
                elapsed = (time.time() - start) * 1000
                if res == 0:
                    self.result.emit(port, '开放', elapsed, get_service_name(port))
                elif not self.fast_mode:
                    self.result.emit(port, '关闭', 0.0, get_service_name(port))
            except Exception:
                if not self.fast_mode:
                    self.result.emit(port, '关闭', 0.0, get_service_name(port))
            finally:
                sock.close()
            self.progress.emit(1)
            task_queue.task_done()

    def run(self):
        """Populate the queue, start workers, and emit completion when done."""
        task_queue = Queue()
        for port in self.ports:
            task_queue.put(port)
        thread_list = []
        for _ in range(min(self.threads, len(self.ports))):
            t = threading.Thread(target=self.scan_worker, args=(task_queue,))
            t.daemon = True
            t.start()
            thread_list.append(t)
        task_queue.join()
        self.running = False
        for t in thread_list:
            t.join(timeout=0.1)
        self.finish.emit()

    def stop(self):
        """Request that workers stop after their current task."""
        self.running = False

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("本机端口自动扫描系统（增强GUI大表格超高速版）")
        self.resize(1200, 800)
        self.thread_level = 120
        self.init_ui()
        self.scan_thread = None
        self.scanned_results = []
        self.only_open = True
        self.invalid_ports_tip = ''

    def init_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setSpacing(12)
        banner = QLabel("⏫ 本机端口自动扫描系统【增强版 GUI & 极速√】 ⏫")
        banner.setAlignment(Qt.AlignCenter)
        banner.setStyleSheet("font-size:30px; font-weight:bold; color:#1274df; background:#f3fbfe; border-radius:12px; padding:13px;")
        sub_banner = QLabel("绿色合规 · 技术交流 · 拒绝非法用途")
        sub_banner.setAlignment(Qt.AlignCenter)
        sub_banner.setStyleSheet("font-size:15px; color:#f6861f; font-weight:bold; margin-bottom:6px;")
        main_layout.addWidget(banner)
        main_layout.addWidget(sub_banner)

        sys_box = QHBoxLayout()
        host_info = QVBoxLayout()
        l1 = QLabel("主机名    ：")
        l2 = QLabel("本地IP    ：")
        self.val_host = QLabel(get_hostname())
        self.val_ip = QLabel(get_local_ip())
        for x in [l1, l2]:
            x.setStyleSheet("font-weight:bold; color:#1c82b6; font-size:16px;")
        for y in [self.val_host, self.val_ip]:
            y.setStyleSheet("color:#222; font-weight:bold; font-size:16px;")
        host_info.addWidget(l1); host_info.addWidget(self.val_host)
        host_info.addWidget(l2); host_info.addWidget(self.val_ip)
        sys_detail = QTextEdit()
        sys_detail.setReadOnly(True)
        sys_detail.setText(get_os_details())
        sys_detail.setFixedHeight(95)
        sys_detail.setStyleSheet("background:#fcf3e6; border-radius:8px; font-size:14px; font-family:'Consolas'; color:#615548; font-weight:bold;")
        sys_box.addLayout(host_info)
        sys_box.addWidget(sys_detail)
        main_layout.addLayout(sys_box)

        port_box = QHBoxLayout()
        self.section_port = QLabel("【端口选择】")
        self.section_port.setStyleSheet("font-size:19px; color:#22ad7a; margin-top:8px; font-weight:bold;")
        self.ports_input = QLineEdit()
        self.ports_input.setPlaceholderText("端口如 80,443 或 1000-1010 (留空为默认)")
        self.ports_input.setStyleSheet("background:#eaf8ef; border-radius:6px; font-size:16px;")
        self.chk_all = QCheckBox("全部1-65535端口 (极慢/高危资源消耗, 谨慎)")
        self.chk_all.setStyleSheet("color:#e32b38; font-weight:bold; font-size:13px; margin-left:13px;")
        port_box.addWidget(self.section_port)
        port_box.addWidget(self.ports_input)
        port_box.addWidget(self.chk_all)
        main_layout.addLayout(port_box)

        adv_set_box = QHBoxLayout()
        self.lbl_threads = QLabel("扫描线程数(10~300)：")
        self.lbl_threads.setStyleSheet("font-size:15px; color:#722cc1; font-weight:bold;")
        self.thread_input = QLineEdit(str(self.thread_level))
        self.thread_input.setFixedWidth(45)
        self.thread_input.setStyleSheet("background:#e2e2fc; border-radius:4px;font-size:15px;text-align:center;")
        self.chk_fast = QCheckBox("极速模式（只显示开放端口）")
        self.chk_fast.setStyleSheet("color:#9b4fe2; font-weight:bold; font-size:15px; margin-left:18px;")
        adv_set_box.addWidget(self.lbl_threads)
        adv_set_box.addWidget(self.thread_input)
        adv_set_box.addWidget(self.chk_fast)
        main_layout.addLayout(adv_set_box)

        self.btn_start = QPushButton("▶ 开始扫描")
        self.btn_start.setStyleSheet("background:#179be7; color:#fff; font-size:23px; font-weight:bold; border-radius:7px; padding:10px;")
        self.btn_start.clicked.connect(self.start_scan)
        self.btn_start.setCursor(Qt.PointingHandCursor)
        main_layout.addWidget(self.btn_start)

        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.progress.setVisible(False)
        self.progress.setStyleSheet("height:26px; font-size:15px;")
        main_layout.addWidget(self.progress)

        self.tip_box = QLabel('')
        self.tip_box.setStyleSheet("font-size:14px; font-weight:bold; color:#f44516; padding:6px;")
        main_layout.addWidget(self.tip_box)

        result_switch_box = QHBoxLayout()
        self.btn_show_open = QPushButton("只看开放端口")
        self.btn_show_open.setCheckable(True)
        self.btn_show_open.setChecked(True)
        self.btn_show_open.setStyleSheet("background:#33B369; color:white; border-radius:5px; font-weight:bold; font-size:15px;")
        self.btn_show_open.clicked.connect(self.toggle_result_view)
        self.btn_show_all = QPushButton("显示所有端口")
        self.btn_show_all.setCheckable(True)
        self.btn_show_all.setChecked(False)
        self.btn_show_all.setStyleSheet("background:#999; color:white; border-radius:5px; font-weight:bold; font-size:15px;")
        self.btn_show_all.clicked.connect(self.toggle_result_view)
        result_switch_box.addWidget(self.btn_show_open)
        result_switch_box.addWidget(self.btn_show_all)
        result_switch_box.addStretch(2)
        main_layout.addLayout(result_switch_box)

        section_result = QLabel("【端口扫描结果】(可拖动/放大)")
        section_result.setStyleSheet("font-size:18px; color:#414fa0; font-weight:bold;")
        main_layout.addWidget(section_result)
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setRowCount(0)
        self.table.setHorizontalHeaderLabels(['端口','状态','耗时(ms)','服务/协议'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setDefaultSectionSize(120)
        self.table.verticalHeader().setDefaultSectionSize(32)
        self.table.setStyleSheet("""
            font-size:18px;
            selection-background-color:#e9f9ed;
            alternate-background-color: #fafbff;
        """)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setShowGrid(True)
        self.table.setAlternatingRowColors(True)
        self.table.setMinimumHeight(420)
        main_layout.addWidget(self.table)

        btn_box = QHBoxLayout()
        self.btn_save = QPushButton("保存结果")
        self.btn_save.setStyleSheet("background:#259ee7; color:white; font-weight:bold; border-radius:5px; font-size:16px;")
        self.btn_save.setCursor(Qt.PointingHandCursor)
        self.btn_save.setEnabled(False)
        self.btn_save.clicked.connect(self.save_results)
        self.btn_clear = QPushButton("清空结果")
        self.btn_clear.setStyleSheet("background:#999; color:white; font-weight:bold; border-radius:5px; font-size:16px;")
        self.btn_clear.setCursor(Qt.PointingHandCursor)
        self.btn_clear.setEnabled(False)
        self.btn_clear.clicked.connect(self.clear_table)
        btn_box.addWidget(self.btn_save)
        btn_box.addWidget(self.btn_clear)
        btn_box.addStretch(5)
        main_layout.addLayout(btn_box)

        self.note = QLabel("感谢使用本工具，绿色合规，禁止非法用途。")
        self.note.setStyleSheet("font-size:16px; color:#17ad54; background:#e2ffe0; border-radius:8px; padding:9px; margin-top:9px; margin-bottom:3px;")
        self.note.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.note)

        self.setLayout(main_layout)

    def get_ports(self):
        """Parse the port input or return the selected scan range."""
        self.invalid_ports_tip = ''
        if self.chk_all.isChecked():
            return list(range(1,65536))
        s = self.ports_input.text().strip()
        if not s:
            return self.default_ports()
        ports = set()
        invalid_parts = []
        for part in s.replace(',', ' ').split():
            try:
                if '-' in part:
                    start, end = map(int, part.split('-', 1))
                    if not 1 <= start <= 65535 or not 1 <= end <= 65535:
                        raise ValueError
                    ports.update(range(min(start, end), max(start, end) + 1))
                else:
                    port = int(part)
                    if not 1 <= port <= 65535:
                        raise ValueError
                    ports.add(port)
            except ValueError:
                invalid_parts.append(part)
        if invalid_parts:
            self.invalid_ports_tip = "已忽略无效端口：" + ", ".join(invalid_parts[:5])
            self.tip_box.setText(self.invalid_ports_tip)
        return sorted(ports)

    def default_ports(self):
        """Return the built-in common ports and the standard system range."""
        return sorted(set(
            [21,22,23,25,53,80,110,135,139,143,443,445,1433,1521,
             3306,3389,6379,8080,8888,9000] + list(range(1,1025))
        ))

    def get_thread_count(self):
        """Return the clamped worker count, defaulting invalid input to 100."""
        userv = self.thread_input.text().strip()
        try:
            v = int(userv)
        except ValueError:
            v = 100
        return min(max(v, 10), 300)

    def start_scan(self):
        if self.scan_thread and self.scan_thread.isRunning():
            QMessageBox.warning(self, "请等待", "扫描还未结束！")
            return
        ports = self.get_ports()
        if not ports:
            QMessageBox.warning(self, "错误", "请输入有效端口！")
            return
        if len(ports) > 4096:
            if QMessageBox.question(self, "大端口数量",
                f"本次实际要扫描 {len(ports)} 个端口，可能很慢。是否继续？",
                QMessageBox.Yes|QMessageBox.No) == QMessageBox.No:
                return
        self.table.setRowCount(0)
        self.scanned_results = []
        self.progress.setMaximum(len(ports))
        self.progress.setValue(0)
        self.progress.setVisible(True)
        scan_tip = "正在扫描，请稍候..."
        if self.invalid_ports_tip:
            scan_tip += f"（{self.invalid_ports_tip}）"
        self.tip_box.setText(scan_tip)
        self.btn_start.setEnabled(False)
        self.btn_save.setEnabled(False)
        self.btn_clear.setEnabled(False)
        self.chk_all.setEnabled(False)
        self.chk_fast.setEnabled(False)
        self.ports_input.setEnabled(False)
        self.thread_input.setEnabled(False)
        self.btn_show_open.setEnabled(False)
        self.btn_show_all.setEnabled(False)
        threads = self.get_thread_count()
        self.scan_thread = PortScannerThread(get_local_ip(), ports, self.chk_fast.isChecked(), threads)
        self.scan_thread.progress.connect(self.on_progress)
        self.scan_thread.result.connect(self.on_result)
        self.scan_thread.finish.connect(self.on_finish)
        self.scan_thread.start()
        self.current_scan_ports = ports

    @pyqtSlot(int)
    def on_progress(self, value):
        p = self.progress.value()
        self.progress.setValue(p+1)
        progress_tip = f"已扫 {p+1}/{self.progress.maximum()}..."
        if self.invalid_ports_tip:
            progress_tip += f"（{self.invalid_ports_tip}）"
        self.tip_box.setText(progress_tip)

    @pyqtSlot(int, str, float, str)
    def on_result(self, port, state, elapsed, service):
        self.scanned_results.append((port, state, elapsed, service))
        if self.only_open:
            if state == '开放':
                self._add_row(port, state, elapsed, service)
        else:
            self._add_row(port, state, elapsed, service)

    def _add_row(self, port, state, elapsed, service):
        row = self.table.rowCount()
        self.table.insertRow(row)
        cell_port = QTableWidgetItem(str(port))
        cell1 = QTableWidgetItem(state)
        if state == '开放':
            cell1.setForeground(Qt.green)
            cell1.setBackground(Qt.white)
            cell_port.setForeground(Qt.blue)
        self.table.setItem(row, 0, cell_port)
        self.table.setItem(row, 1, cell1)
        self.table.setItem(row, 2, QTableWidgetItem(f"{elapsed:.1f}" if elapsed > 0 else '-'))
        self.table.setItem(row, 3, QTableWidgetItem(service))
        if state == '开放':
            self.table.scrollToBottom()

    @pyqtSlot()
    def on_finish(self):
        open_count = sum(1 for p,s,_,_ in self.scanned_results if s == '开放')
        finish_tip = f"【扫描完毕】开放端口{open_count}个 / 扫描端口{len(self.scanned_results)}个。(↑点击切换显示全部/只看开放)"
        if self.invalid_ports_tip:
            finish_tip += f"（{self.invalid_ports_tip}）"
        self.tip_box.setText(finish_tip)
        self.btn_start.setEnabled(True)
        self.btn_save.setEnabled(True)
        self.btn_clear.setEnabled(True)
        self.chk_all.setEnabled(True)
        self.chk_fast.setEnabled(True)
        self.ports_input.setEnabled(True)
        self.thread_input.setEnabled(True)
        self.btn_show_open.setEnabled(True)
        self.btn_show_all.setEnabled(True)
        self.progress.setVisible(False)

    def show_results_view(self):
        self.table.setRowCount(0)
        if self.only_open:
            shown = [i for i in self.scanned_results if i[1] == "开放"]
        else:
            shown = self.scanned_results
        for port, state, elapsed, svc in shown:
            self._add_row(port, state, elapsed, svc)

    def toggle_result_view(self):
        if self.sender() == self.btn_show_open:
            self.only_open = True
            self.btn_show_open.setChecked(True)
            self.btn_show_all.setChecked(False)
            self.btn_show_open.setStyleSheet("background:#33B369; color:white; border-radius:5px; font-weight:bold; font-size:15px;")
            self.btn_show_all.setStyleSheet("background:#999; color:white; border-radius:5px; font-weight:bold; font-size:15px;")
        else:
            self.only_open = False
            self.btn_show_open.setChecked(False)
            self.btn_show_all.setChecked(True)
            self.btn_show_open.setStyleSheet("background:#999; color:white; border-radius:5px; font-weight:bold; font-size:15px;")
            self.btn_show_all.setStyleSheet("background:#3377E8; color:white; border-radius:5px; font-weight:bold; font-size:15px;")
        self.show_results_view()

    def save_results(self):
        if not self.scanned_results:
            QMessageBox.information(self,"提示","结果为空")
            return
        fname, _ = QFileDialog.getSaveFileName(self, "保存结果", "port_scan_results.txt", "文本文件 (*.txt);;所有文件 (*.*)")
        if fname:
            try:
                with open(fname, 'w', encoding='utf-8') as f:
                    f.write(f"{'端口':<8} {'状态':<6} {'耗时':<9} {'服务/协议'}\n")
                    for port, state, elapsed, svc in self.scanned_results:
                        t = f"{port:<8} {state:<6} {f'{elapsed:.1f}':<9} {svc}\n" if elapsed > 0 else f"{port:<8} {state:<6} {'-':<9} {svc}\n"
                        f.write(t)
                QMessageBox.information(self,"保存成功",f"已保存至：{fname}")
            except Exception as e:
                QMessageBox.warning(self, "保存失败", f"写入异常: {e}")

    def clear_table(self):
        self.table.setRowCount(0)
        self.scanned_results = []
        self.invalid_ports_tip = ''
        self.tip_box.setText('')

    def closeEvent(self, e):
        if self.scan_thread and self.scan_thread.isRunning():
            self.scan_thread.stop()
            self.scan_thread.wait()
        e.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())