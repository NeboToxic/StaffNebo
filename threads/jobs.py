from PyQt5.QtCore import pyqtSignal
from threads.base import StoppableThread


class JobThread(StoppableThread):
    done=pyqtSignal(bool,object)
    progress=pyqtSignal(int)

    def __init__(self,function,parent=None):
        super().__init__(parent)
        self.function=function

    def run(self):
        try:
            result=self.function(lambda:self.should_stop,self.progress.emit)
            self.done.emit(True,result)
        except Exception as exc:self.done.emit(False,str(exc))
