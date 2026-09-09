"""Small PySide6 observer/controller for the managed serial service."""
import base64, sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication,QComboBox,QFormLayout,QHBoxLayout,QLabel,QLineEdit,QMainWindow,QMessageBox,QPlainTextEdit,QPushButton,QVBoxLayout,QWidget
from serial_client import Client
from serial_commands import StreamBuffer,parse_command

class SerialWindow(QMainWindow):
    def __init__(self,host='127.0.0.1',control=8889,tcp=8888,autostart=True):
        super().__init__(); self.setWindowTitle('Shared Serial Debug'); self.buffer=StreamBuffer(); self.state=None
        self.client=Client(host,control); self.client.subscribe(); self.port=QLineEdit(); self.baud=QComboBox(); self.baud.setEditable(True); self.baud.addItems(['9600','19200','38400','57600','115200','230400','460800','921600'])
        self.rx=QPlainTextEdit(); self.rx.setReadOnly(True); self.command=QLineEdit(); self.command.setPlaceholderText('status | send {"data":"help","newline":"cr"}')
        self.encoding=QComboBox(); self.encoding.addItems(['utf-8','ascii']); self.newline=QComboBox(); self.newline.addItems(['none','cr','lf','crlf']); self.hex_mode=QComboBox(); self.hex_mode.addItems(['text','hex'])
        self.send_button=QPushButton('Send'); self.takeover=QPushButton('Terminate Agent and Take Over'); self.connect_button=QPushButton('Open'); self.release_button=QPushButton('Release device'); self.status_label=QLabel('Connecting…')
        form=QFormLayout(); form.addRow('Port',self.port); form.addRow('Baud',self.baud); form.addRow('Encoding',self.encoding); form.addRow('Line ending',self.newline); form.addRow('Send mode',self.hex_mode); buttons=QHBoxLayout()
        for b in (self.connect_button,self.release_button,self.takeover): buttons.addWidget(b)
        layout=QVBoxLayout(); layout.addWidget(self.status_label); layout.addLayout(form); layout.addLayout(buttons); layout.addWidget(self.rx); layout.addWidget(self.command); layout.addWidget(self.send_button); wrapper=QWidget(); wrapper.setLayout(layout); self.setCentralWidget(wrapper)
        self.send_button.clicked.connect(self.send_command); self.command.returnPressed.connect(self.send_command); self.connect_button.clicked.connect(lambda:self.action('serial.open',port=self.port.text(),baudrate=int(self.baud.currentText()))); self.release_button.clicked.connect(lambda:self.action('serial.close')); self.takeover.clicked.connect(self.takeover_agent)
        self.timer=QTimer(self); self.timer.timeout.connect(self.poll_events); self.timer.start(30); self.refresh_state(self.client.call('status'))
    def action(self,name,**params):
        try:
            self.refresh_state(self.client.call(name,**params))
            if name == 'agent.takeover':
                self.refresh_state(self.client.call('status'))
                self.send_button.setEnabled(bool(self.state.get('connected')))
                self.connect_button.setEnabled(True); self.release_button.setEnabled(True); self.takeover.setEnabled(False)
        except Exception as e:QMessageBox.warning(self,'Serial service',str(e))
    def takeover_agent(self):
        self.action('agent.takeover')
    def send_command(self):
        try:
            action,params=parse_command(self.command.text())
            if action=='clear':self.buffer.clear();self.rx.clear();return
            if action == 'send': params.setdefault('encoding', self.encoding.currentText()); params.setdefault('newline', self.newline.currentText())
            if action == 'send' and self.hex_mode.currentText() == 'hex': action = 'send.hex'; params = {'data': params.get('data','')}
            self.refresh_state(self.client.call(action,**params));self.command.clear()
        except Exception as e:QMessageBox.warning(self,'Command',str(e))
    def poll_events(self):
        while True:
            try:e=self.client.next_event(0)
            except Exception:break
            if e.get('event') in ('rx','tx'):self.buffer.append(e['event'],base64.b64decode(e['data']))
            elif e.get('event')=='state':self.refresh_state(e.get('state',{}))
        self.rx.setPlainText(self.buffer.render())
    def refresh_state(self,s):
        self.state=s; c=s.get('config',{}); self.port.setText(str(c.get('port') or '')); self.baud.setCurrentText(str(c.get('baudrate',115200))); owner=s.get('owner','human'); self.status_label.setText(f"Service: connected | Device: {'connected' if s.get('connected') else 'released'} | Owner: {owner}"); self.send_button.setEnabled(owner=='human' and s.get('connected',False)); self.connect_button.setEnabled(owner=='human'); self.release_button.setEnabled(owner=='human'); self.takeover.setEnabled(owner=='agent')
    def closeEvent(self,e):self.timer.stop();self.client.close();e.accept()
def main():
    app=QApplication(sys.argv); w=SerialWindow(); w.show(); return app.exec()
if __name__=='__main__':sys.exit(main())
