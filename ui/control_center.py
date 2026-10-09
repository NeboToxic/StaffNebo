import datetime
import json
from pathlib import Path
from dataclasses import asdict
from PyQt5.QtCore import Qt, QDate, QTimer, QUrl, pyqtSignal
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QTabWidget,QWidget,
    QLabel,QPushButton,QLineEdit,QComboBox,QCheckBox,QTextEdit,QTableWidget,QTableWidgetItem,
    QFileDialog,QMessageBox,QDateEdit,QScrollArea,QProgressBar,QAbstractItemView,QSpinBox)
from core import history,profiles
from core.database import get_meta
from core.settings import AppSettings,load_settings,save_settings,clear_saved_secrets
from core.secrets import redact,FIELDS
from domain.events import PunishmentType
from domain.notifier import SendPayload
from domain.templates import DEFAULT_TEMPLATE,validate_template,render_template
from domain.capture import monitors,windows
from threads.delivery import DeliveryThread
from threads.jobs import JobThread
from services.connections import check_connection
from services.diagnostics import export_diagnostics
from services.updates import check_update,download_update

STATES={'pending':'Ожидает','sending':'Отправляется','sent':'Доставлено','failed':'Ошибка','disabled':'Отключено'}
KINDS={'mute':'Мут','warn':'Варн','kick':'Кик','screenshot':'Скриншот'}


class ControlCenter(QDialog):
    profile_changed=pyqtSignal()

    def __init__(self,parent=None):
        super().__init__(parent)
        self.owner=parent;self._jobs=set();self._closing=False;self._update=None;self._profile_key=None
        profiles.ensure_default();history.init_history()
        self.setWindowTitle('NeboProject — Центр управления');self.resize(1100,730);self.setMinimumSize(760,520)
        self.setStyleSheet("""QDialog,QWidget {background:#13131b;color:#eeeeef;font-size:13px;}
            QLineEdit,QComboBox,QTextEdit,QTableWidget,QDateEdit,QSpinBox {background:#20202b;border:1px solid #454554;padding:6px;selection-background-color:#cc2544;}
            QPushButton {background:#343441;border:1px solid #555565;border-radius:5px;padding:7px 12px;}
            QPushButton:hover {background:#562738;} QPushButton:disabled {color:#777;}
            QTabBar::tab {padding:10px;background:#20202b;} QTabBar::tab:selected {background:#562738;}
            QHeaderView::section {background:#343441;padding:5px;} QScrollArea {border:0;}
            QCheckBox::indicator {width:16px;height:16px;}""")
        layout=QVBoxLayout(self);self.tabs=QTabWidget();layout.addWidget(self.tabs)
        self._history_tab();self._outbox_tab();self._connection_tab();self._profiles_tab()
        self._notification_tab();self._capture_tab();self._stats_tab();self._diagnostic_tab();self._updates_tab()
        self.tabs.currentChanged.connect(lambda _:self.refresh())
        self._timer=QTimer(self);self._timer.setInterval(2000);self._timer.timeout.connect(self.refresh);self._timer.start()
        self.refresh_profiles();self.refresh()

    def page(self,title):
        scroll=QScrollArea();scroll.setWidgetResizable(True);widget=QWidget();layout=QVBoxLayout(widget)
        scroll.setWidget(widget);self.tabs.addTab(scroll,title);return layout

    def button(self,text,callback,layout):
        button=QPushButton(text);button.clicked.connect(lambda:self.guard(callback));layout.addWidget(button);return button

    def guard(self,callback):
        try:return callback()
        except Exception as exc:
            try:cfg=load_settings();known=[getattr(cfg,k) for k in FIELDS]
            except Exception:known=[]
            QMessageBox.warning(self,'NeboProject',redact(exc,known))

    def main(self):return getattr(self.owner,'_main_screen',None)

    def require_idle(self):
        main=self.main()
        if self.has_running_threads() or (main and (main.ops.is_busy or main._screenshot_busy)):raise ValueError('Дождитесь завершения текущей отправки перед сменой настроек.')

    def track(self,job):
        self._jobs.add(job);job.finished.connect(lambda j=job:self.release(j));job.start();return job

    def release(self,job):self._jobs.discard(job);job.deleteLater()
    def has_running_threads(self):return any(j.isRunning() for j in self._jobs)
    def stop_jobs(self):
        self._closing=True
        for job in tuple(self._jobs):job.stop()
    def closeEvent(self,event):
        self.stop_jobs()
        if self.has_running_threads():
            event.ignore();QTimer.singleShot(100,self.close);return
        self._timer.stop();event.accept()
    def showEvent(self,event):
        self._closing=False;self._timer.start();self.refresh()
        if not self.has_running_threads():
            self.connection_button.setEnabled(True);self.update_check.setEnabled(True)
            self.update_download.setEnabled(bool(self._update and self._update['new']))
        super().showEvent(event)

    def table(self,layout,headers):
        table=QTableWidget(0,len(headers));table.setHorizontalHeaderLabels(headers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows);table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers);table.setMinimumHeight(280)
        table.horizontalHeader().setStretchLastSection(True);layout.addWidget(table);return table

    def fill(self,table,rows):
        selected=self.selected(table,required=False);table.setRowCount(len(rows))
        for i,row in enumerate(rows):
            values=[row['id'],row['created'],KINDS.get(row['event_type'],row['event_type']),row['target'],
                    row['reason'],row['profile_name'],STATES.get(row['status'],row['status']),row['error']]
            for j,value in enumerate(values):table.setItem(i,j,QTableWidgetItem(str(value)))
            if row['id']==selected:table.selectRow(i)
        for col,width in [(0,55),(1,175),(2,85),(3,130),(4,190),(5,120),(6,105)]:table.setColumnWidth(col,width)

    def selected(self,table,required=True):
        row=table.currentRow()
        if row<0 or table.item(row,0) is None:
            if required:raise ValueError('Выберите событие в таблице')
            return None
        return int(table.item(row,0).text())

    def _history_tab(self):
        layout=self.page('История');bar=QHBoxLayout();layout.addLayout(bar)
        self.search=QLineEdit();self.search.setPlaceholderText('Ник, модератор или причина');bar.addWidget(self.search)
        self.kind=QComboBox();self.kind.addItem('Все типы','')
        for key,title in KINDS.items():self.kind.addItem(title,key)
        bar.addWidget(self.kind);self.state=QComboBox();self.state.addItem('Все статусы','')
        for key,title in STATES.items():self.state.addItem(title,key)
        bar.addWidget(self.state);self.history_profile=QComboBox();bar.addWidget(self.history_profile)
        dates=QHBoxLayout();layout.addLayout(dates);self.date_filter=QCheckBox('За период');dates.addWidget(self.date_filter)
        self.since=QDateEdit(QDate.currentDate().addDays(-6));self.until=QDateEdit(QDate.currentDate())
        for field in (self.since,self.until):field.setCalendarPopup(True);dates.addWidget(field)
        self.button('Найти',self.refresh_history,dates);self.button('Экспорт CSV',self.export_history,dates)
        self.history_table=self.table(layout,['ID','Дата','Тип','Ник','Причина','Профиль','Статус','Ошибка'])
        actions=QHBoxLayout();layout.addLayout(actions)
        self.button('Открыть скриншот',lambda:self.open_screenshot(self.history_table),actions)
        layout.addWidget(QLabel('Таблица показывает последние 1000 совпадений. CSV содержит все события по выбранным фильтрам.'))
        self.search.returnPressed.connect(self.refresh_history)

    def filters(self):
        return {'query':self.search.text().strip(),'kind':self.kind.currentData(),'status':self.state.currentData(),
                'profile':self.history_profile.currentData() or '',
                'since':self.since.date().toString('yyyy-MM-dd') if self.date_filter.isChecked() else '',
                'until':self.until.date().toString('yyyy-MM-dd') if self.date_filter.isChecked() else ''}
    def refresh_history(self):self.fill(self.history_table,history.list_events(**self.filters()))
    def export_history(self):
        file,_=QFileDialog.getSaveFileName(self,'Экспорт истории','history.csv','CSV (*.csv)')
        if file:count=history.export_csv(file,**self.filters());QMessageBox.information(self,'Экспорт',f'Сохранено событий: {count}')
    def open_screenshot(self,table):
        row=history.get_event(self.selected(table));file=row['screenshot_path']
        if not file or not Path(file).is_file():raise ValueError('Скриншот отсутствует или удалён')
        QDesktopServices.openUrl(QUrl.fromLocalFile(file))

    def _outbox_tab(self):
        layout=self.page('Неотправленные')
        layout.addWidget(QLabel('События сохраняются между запусками. По умолчанию повтор использует исходный профиль и получателя.'))
        self.current_retry=QCheckBox('Использовать текущие настройки отправки вместо исходных');layout.addWidget(self.current_retry)
        self.outbox_table=self.table(layout,['ID','Дата','Тип','Ник','Причина','Профиль','Статус','Ошибка'])
        bar=QHBoxLayout();layout.addLayout(bar)
        self.button('Повторить',lambda:self.retry(False),bar);self.button('Повторить без фото',lambda:self.retry(True),bar)
        self.button('Открыть скриншот',lambda:self.open_screenshot(self.outbox_table),bar)
        self.button('Обновить',self.refresh_outbox,bar)
    def refresh_outbox(self):
        self.fill(self.outbox_table,[r for r in history.list_events(limit=2000) if r['status'] in ('pending','failed','sending')])
    def retry(self,without_photo):
        key=self.selected(self.outbox_table);row=history.get_event(key)
        if row['status']=='sending':raise ValueError('Событие уже отправляется')
        if without_photo and row['event_type']=='screenshot':raise ValueError('Ручной скриншот нельзя отправить без изображения')
        if self.current_retry.isChecked():history.replace_delivery_settings(key,load_settings())
        job=DeliveryThread(key,without_photo);job.finished_signal.connect(self.retry_done);self.track(job)
    def retry_done(self,ok,message):
        if self._closing or getattr(self.owner,'_closing',False):return
        self.refresh()
        if not ok:QMessageBox.warning(self,'Повторная отправка',message)
        main=self.main()
        if main:main.log_message(message);main.update_stats()

    def _connection_tab(self):
        layout=self.page('Подключение')
        layout.addWidget(QLabel('Проверка активного профиля. Telegram: токен, доступность чата и прокси. VK: доступ к загрузке фото для указанного получателя.'))
        self.connection_info=QLabel();self.connection_info.setWordWrap(True);layout.addWidget(self.connection_info)
        self.connection_button=self.button('Проверить подключение',self.test_connection,layout)
        self.connection_result=QTextEdit();self.connection_result.setReadOnly(True);layout.addWidget(self.connection_result)
    def test_connection(self):
        settings=load_settings();self.connection_button.setEnabled(False);self.connection_result.setPlainText('Проверка…')
        job=JobThread(lambda cancel,progress:check_connection(settings,cancel));job.done.connect(self.connection_done);self.track(job)
    def connection_done(self,ok,result):
        if self._closing or getattr(self.owner,'_closing',False):return
        self.connection_button.setEnabled(True)
        if ok:success,message=result;self.connection_result.setPlainText(('✅ ' if success else '❌ ')+message)
        else:self.connection_result.setPlainText(str(result))

    def secret_field(self,form,label):
        row=QHBoxLayout();field=QLineEdit();field.setEchoMode(QLineEdit.Password);row.addWidget(field)
        button=QPushButton('Показать');button.setCheckable(True)
        button.toggled.connect(lambda checked:field.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password));row.addWidget(button)
        form.addRow(label,row);return field

    def _profiles_tab(self):
        layout=self.page('Профили');bar=QHBoxLayout();layout.addLayout(bar)
        self.profile_list=QComboBox();bar.addWidget(self.profile_list);self.profile_list.currentIndexChanged.connect(self.load_editor)
        self.button('Новый',self.new_profile,bar);self.button('Копия текущего',self.clone_profile,bar)
        self.button('Удалить профиль',self.remove_profile,bar)
        self.active_label=QLabel();layout.addWidget(self.active_label)
        form=QFormLayout();layout.addLayout(form);self.profile_name=QLineEdit();form.addRow('Название / сервер',self.profile_name)
        self.profile_nick=QLineEdit();form.addRow('Ник модератора',self.profile_nick)
        pathrow=QHBoxLayout();self.profile_logs=QLineEdit();pathrow.addWidget(self.profile_logs)
        self.button('Выбрать файл',self.browse_logs,pathrow);form.addRow('latest.log',pathrow)
        self.profile_platform=QComboBox();self.profile_platform.addItem('Telegram','telegram');self.profile_platform.addItem('VK','vk');form.addRow('Сервис',self.profile_platform)
        self.profile_bot=self.secret_field(form,'Telegram Bot Token');self.profile_chat=QLineEdit();form.addRow('Telegram Chat ID',self.profile_chat)
        self.profile_vk=self.secret_field(form,'VK Token');self.profile_peer=QLineEdit();form.addRow('VK ID получателя',self.profile_peer)
        self.proxy_type=QComboBox();self.proxy_type.addItems(['none','http','socks5']);form.addRow('Прокси Telegram',self.proxy_type)
        self.proxy_host=QLineEdit();form.addRow('Адрес прокси',self.proxy_host);self.proxy_port=QLineEdit();form.addRow('Порт',self.proxy_port)
        self.proxy_user=QLineEdit();form.addRow('Логин прокси',self.proxy_user);self.proxy_pass=self.secret_field(form,'Пароль прокси')
        bar=QHBoxLayout();layout.addLayout(bar);self.button('Сохранить профиль',self.save_editor,bar);self.button('Переключиться на профиль',self.activate_editor,bar)
        self.button('Удалить все сохранённые секреты',self.clear_secrets,layout)
        layout.addWidget(QLabel('Токены и пароль прокси защищены DPAPI текущего аккаунта Windows. База не переносит эти секреты на другой аккаунт.'))

    def refresh_profiles(self):
        history_selected=self.history_profile.currentData();selected=self.profile_list.currentData();self.profile_list.blockSignals(True);self.profile_list.clear()
        active=get_meta('active_profile','');self.history_profile.clear();self.history_profile.addItem('Все профили','')
        for row in profiles.list_profiles():
            self.profile_list.addItem(row['name'],row['id']);self.history_profile.addItem(row['name'],row['id'])
        index=self.profile_list.findData(selected or active);self.profile_list.setCurrentIndex(max(0,index));self.profile_list.blockSignals(False)
        self.history_profile.setCurrentIndex(max(0,self.history_profile.findData(history_selected)))
        self.load_editor();self.active_label.setText('Активный профиль: '+next((r['name'] for r in profiles.list_profiles() if r['id']==active),'Основной'))

    def load_editor(self):
        key=self.profile_list.currentData()
        if not key:return
        self.guard(lambda:self.populate_profile(*profiles.load_profile(key),key))
    def populate_profile(self,name,cfg,key):
        self._profile_key=key;self._editor_settings=cfg
        for field,value in [(self.profile_name,name),(self.profile_nick,cfg.nick),(self.profile_logs,cfg.logs),
            (self.profile_bot,cfg.bot_id),(self.profile_chat,cfg.chat_id),(self.profile_vk,cfg.vk_token),(self.profile_peer,cfg.vk_user_id),
            (self.proxy_host,cfg.tg_proxy_host),(self.proxy_port,cfg.tg_proxy_port),(self.proxy_user,cfg.tg_proxy_username),(self.proxy_pass,cfg.tg_proxy_password)]:field.setText(value or '')
        self.profile_platform.setCurrentIndex(max(0,self.profile_platform.findData(cfg.platform)));self.proxy_type.setCurrentText(cfg.tg_proxy_type)
    def new_profile(self):self.populate_profile('Новый профиль',AppSettings(),None)
    def clone_profile(self):self.populate_profile('Копия профиля',load_settings(),None)
    def browse_logs(self):
        file,_=QFileDialog.getOpenFileName(self,'Выберите latest.log','','Log (*.log);;Все файлы (*)')
        if file:self.profile_logs.setText(file)
    def editor_settings(self):
        cfg=self._editor_settings
        cfg.nick=self.profile_nick.text().strip();cfg.logs=self.profile_logs.text().strip();cfg.platform=self.profile_platform.currentData()
        cfg.bot_id=self.profile_bot.text().strip();cfg.chat_id=self.profile_chat.text().strip();cfg.vk_token=self.profile_vk.text().strip();cfg.vk_user_id=self.profile_peer.text().strip()
        cfg.tg_proxy_type=self.proxy_type.currentText();cfg.tg_proxy_host=self.proxy_host.text().strip();cfg.tg_proxy_port=self.proxy_port.text().strip()
        cfg.tg_proxy_username=self.proxy_user.text();cfg.tg_proxy_password=self.proxy_pass.text()
        cfg.verified_bot_id='';cfg.verified_chat_id=''
        return cfg
    def save_editor(self):
        self.require_idle();cfg=self.editor_settings();key=profiles.save_profile(self.profile_name.text(),cfg,self._profile_key)
        self._profile_key=key
        if key==get_meta('active_profile',''):profiles.activate(key);self.profile_changed.emit();self.reload_preferences()
        self.refresh_profiles();self.profile_list.setCurrentIndex(self.profile_list.findData(key))
    def activate_editor(self):
        self.require_idle()
        if not self._profile_key:raise ValueError('Сначала сохраните новый профиль')
        name,cfg=profiles.load_profile(self._profile_key)
        if not cfg.logs or not Path(cfg.logs).is_file():raise ValueError('В профиле должен быть доступный файл журнала')
        profiles.activate(self._profile_key);self.profile_changed.emit();self.reload_preferences();self.refresh_profiles()
    def remove_profile(self):
        key=self.profile_list.currentData()
        if QMessageBox.question(self,'Удаление профиля','Удалить выбранный профиль? История останется.')==QMessageBox.Yes:
            profiles.delete_profile(key);self.refresh_profiles()
    def clear_secrets(self):
        self.require_idle()
        if QMessageBox.question(self,'Удаление секретов','Удалить токены и пароли прокси из всех профилей и сохранённых уведомлений?')!=QMessageBox.Yes:return
        clear_saved_secrets();self.profile_changed.emit();self.refresh_profiles()

    def _notification_tab(self):
        layout=self.page('Уведомления');form=QFormLayout();layout.addLayout(form);cfg=load_settings();self.notify={};self.photos={}
        for key,title in [('mute','Мут'),('warn','Варн'),('kick','Кик')]:
            row=QHBoxLayout();enabled=QCheckBox('Отправлять');enabled.setChecked(getattr(cfg,'notify_'+key));photo=QCheckBox('Со скриншотом');photo.setChecked(getattr(cfg,'photo_'+key))
            row.addWidget(enabled);row.addWidget(photo);form.addRow(title,row);self.notify[key]=enabled;self.photos[key]=photo
        layout.addWidget(QLabel('Поля: {target}, {type}, {reason}, {date}, {time}, {moderator}, {profile}. HTML в шаблоне отображается как обычный текст.'))
        self.template=QTextEdit();self.template.setPlainText(cfg.notification_template or DEFAULT_TEMPLATE);layout.addWidget(self.template)
        self.preview=QTextEdit();self.preview.setReadOnly(True);layout.addWidget(self.preview)
        self.template.textChanged.connect(lambda:self.guard(self.preview_template))
        bar=QHBoxLayout();layout.addLayout(bar);self.button('Предпросмотр',self.preview_template,bar);self.button('Сохранить',self.save_notifications,bar)
        self.preview_template()
    def preview_template(self):
        cfg=load_settings();cfg.notification_template=self.template.toPlainText()
        try:
            payload=SendPayload(PunishmentType.MUTE,'0','<code>Moderator</code>','<code>Player</code>','Флуд в чате','09.10.2026','12:00:00')
            self.preview.setPlainText(render_template(payload,cfg))
        except ValueError as exc:self.preview.setPlainText(str(exc))
    def save_notifications(self):
        self.require_idle();cfg=load_settings();cfg.notification_template=validate_template(self.template.toPlainText())
        for key in self.notify:setattr(cfg,'notify_'+key,self.notify[key].isChecked());setattr(cfg,'photo_'+key,self.photos[key].isChecked())
        save_settings(cfg);self.refresh_profiles();QMessageBox.information(self,'Уведомления','Настройки сохранены для активного профиля')

    def _capture_tab(self):
        layout=self.page('Захват');form=QFormLayout();layout.addLayout(form);cfg=load_settings()
        self.capture_mode=QComboBox()
        for label,key in [('Весь рабочий стол','screen'),('Монитор','monitor'),('Окно игры','window')]:self.capture_mode.addItem(label,key)
        self.capture_mode.setCurrentIndex(max(0,self.capture_mode.findData(cfg.capture_mode)));form.addRow('Область',self.capture_mode)
        self.monitor_list=QComboBox();form.addRow('Монитор',self.monitor_list)
        self.window_list=QComboBox();self.window_list.setEditable(True);form.addRow('Название окна / часть названия',self.window_list)
        self.refresh_capture_lists();self.monitor_list.setCurrentIndex(max(0,min(cfg.capture_monitor,self.monitor_list.count()-1)));self.window_list.setEditText(cfg.capture_window_title)
        self.hide_capture=QCheckBox('Скрывать интерфейс NeboProject перед захватом');self.hide_capture.setChecked(cfg.hide_before_capture);layout.addWidget(self.hide_capture)
        self.retain=QCheckBox('Сохранять скриншоты после успешной отправки для истории');self.retain.setChecked(cfg.retain_screenshots);layout.addWidget(self.retain)
        self.capture_delay=QSpinBox();self.capture_delay.setRange(0,10000);self.capture_delay.setValue(int(cfg.screenshot_delay*1000));form.addRow('Задержка захвата, мс',self.capture_delay)
        self.button('Обновить мониторы и окна',self.refresh_capture_lists,layout);self.button('Сохранить область захвата',self.save_capture,layout)
        layout.addWidget(QLabel('Захват окна снимает его видимую область на экране. Игра должна быть открыта и не перекрыта другими окнами.'))
    def refresh_capture_lists(self):
        monitor_index=self.monitor_list.currentIndex();text=self.window_list.currentText();self.monitor_list.clear();self.window_list.clear()
        for i,box in enumerate(monitors()):self.monitor_list.addItem(f'Монитор {i+1}: {box[2]-box[0]}×{box[3]-box[1]} ({box[0]}, {box[1]})',i)
        for _,title in windows():self.window_list.addItem(title)
        self.monitor_list.setCurrentIndex(max(0,monitor_index));self.window_list.setEditText(text)
    def save_capture(self):
        self.require_idle();cfg=load_settings();cfg.capture_mode=self.capture_mode.currentData();cfg.capture_monitor=self.monitor_list.currentIndex()
        cfg.capture_window_title=self.window_list.currentText().strip()
        if cfg.capture_mode=='window' and not cfg.capture_window_title:raise ValueError('Выберите или введите название окна')
        if cfg.capture_mode=='monitor' and cfg.capture_monitor<0:raise ValueError('Монитор не найден')
        cfg.hide_before_capture=self.hide_capture.isChecked();cfg.retain_screenshots=self.retain.isChecked();cfg.screenshot_delay=self.capture_delay.value()/1000
        save_settings(cfg);self.refresh_profiles();QMessageBox.information(self,'Захват','Настройки сохранены')
    def reload_preferences(self):
        cfg=load_settings()
        for key in self.notify:self.notify[key].setChecked(getattr(cfg,'notify_'+key));self.photos[key].setChecked(getattr(cfg,'photo_'+key))
        self.template.setPlainText(cfg.notification_template or DEFAULT_TEMPLATE)
        self.capture_mode.setCurrentIndex(max(0,self.capture_mode.findData(cfg.capture_mode)));self.monitor_list.setCurrentIndex(cfg.capture_monitor)
        self.window_list.setEditText(cfg.capture_window_title);self.hide_capture.setChecked(cfg.hide_before_capture);self.retain.setChecked(cfg.retain_screenshots);self.capture_delay.setValue(int(cfg.screenshot_delay*1000))
        self.repository.setText(cfg.update_repository)

    def _stats_tab(self):
        layout=self.page('Статистика');self.stats_current=QCheckBox('Только активный профиль');layout.addWidget(self.stats_current)
        self.stats_current.toggled.connect(self.refresh_stats);self.stats_text=QTextEdit();self.stats_text.setReadOnly(True);layout.addWidget(self.stats_text)
        self.button('Обновить статистику',self.refresh_stats,layout)
    def refresh_stats(self):
        data=history.statistics(get_meta('active_profile','') if self.stats_current.isChecked() else '')
        text=[]
        for label,name in [('day','Сегодня'),('week','Последние 7 дней')]:
            values=data[label];text.append(name)
            for key,title in KINDS.items():text.append(f'  {title}: {values.get(key,0)}')
            text.append(f"  Успешная доставка: {values['success_rate']}% завершённых отправок")
        text.append('Частые причины за всё время:')
        for row in data['reasons']:text.append(f"  {row['count']} — {row['reason']}")
        self.stats_text.setPlainText('\n'.join(text))

    def _diagnostic_tab(self):
        layout=self.page('Диагностика');layout.addWidget(QLabel('Отчёт содержит версию, зависимости, ошибки и состояние мониторинга. Токены и пароль прокси в него не включаются.'))
        self.button('Экспортировать диагностику JSON',self.diagnostics,layout)
    def diagnostics(self):
        file,_=QFileDialog.getSaveFileName(self,'Диагностика','nebo-diagnostics.json','JSON (*.json)')
        if not file:return
        main=self.main();state={'running':bool(main and main.log_monitor.isRunning()),'busy':bool(main and main.ops.is_busy),'log_exists':bool(main and Path(main.log_monitor.logs_path).is_file())}
        export_diagnostics(file,state);QMessageBox.information(self,'Диагностика','Отчёт сохранён')

    def _updates_tab(self):
        layout=self.page('Обновления');layout.addWidget(QLabel('После публикации на GitHub укажите owner/repository. Для обновления релиз должен содержать *-Windows.zip и SHA256SUMS.txt.'))
        self.repository=QLineEdit(load_settings().update_repository);self.repository.setPlaceholderText('owner/NeboProject');layout.addWidget(self.repository)
        bar=QHBoxLayout();layout.addLayout(bar);self.update_check=self.button('Проверить новую версию',self.check_updates,bar)
        self.update_download=self.button('Скачать с проверкой SHA-256',self.download_updates,bar);self.update_download.setEnabled(False)
        self.update_notes=QTextEdit();self.update_notes.setReadOnly(True);layout.addWidget(self.update_notes)
        self.update_progress=QProgressBar();self.update_progress.setRange(0,100);layout.addWidget(self.update_progress)
    def check_updates(self):
        repo=self.repository.text().strip();self.update_check.setEnabled(False);self._update=None;self.update_download.setEnabled(False)
        def check(cancel,progress):return check_update(repo,cancel)
        job=JobThread(check);job.done.connect(self.update_checked);self.track(job)
    def update_checked(self,ok,result):
        if self._closing or getattr(self.owner,'_closing',False):return
        self.update_check.setEnabled(True)
        if not ok:self.update_notes.setPlainText(str(result));return
        self._update=result;cfg=load_settings();cfg.update_repository=result['repository'];save_settings(cfg)
        self.update_notes.setPlainText(('Доступна новая версия ' if result['new'] else 'Установлена актуальная версия. Последний релиз: ')+result['tag']+'\n\n'+result['notes'])
        self.update_download.setEnabled(result['new'])
    def download_updates(self):
        if not self._update or not self._update['new']:return
        asset=self._update['asset']
        if QMessageBox.question(self,'Скачивание обновления',f"Скачать {self._update['tag']} из {self._update['repository']}?\nФайл: {asset['name']}\nПосле скачивания будет проверен SHA-256. Программа не устанавливает обновление автоматически.")!=QMessageBox.Yes:return
        file,_=QFileDialog.getSaveFileName(self,'Сохранить обновление',asset['name'],'ZIP (*.zip)')
        if not file:return
        info=self._update;self.update_download.setEnabled(False)
        job=JobThread(lambda cancel,progress:download_update(info,file,cancel,progress));job.progress.connect(self.update_progress.setValue);job.done.connect(self.update_downloaded);self.track(job)
    def update_downloaded(self,ok,result):
        if self._closing or getattr(self.owner,'_closing',False):return
        self.update_download.setEnabled(bool(self._update and self._update['new']))
        if ok:QMessageBox.information(self,'Обновление','ZIP сохранён, SHA-256 проверен. Закройте программу и распакуйте новую версию.\n'+str(result))
        else:QMessageBox.warning(self,'Обновление',str(result))

    def refresh(self):
        if not hasattr(self,'history_table'):return
        try:
            index=self.tabs.currentIndex()
            if index==0:self.refresh_history()
            elif index==1:self.refresh_outbox()
            elif index==6:self.refresh_stats()
            cfg=load_settings();self.connection_info.setText(f'Активный сервис: {cfg.platform}; ник: {cfg.nick}; получатель: '+(cfg.chat_id if cfg.platform=='telegram' else cfg.vk_user_id))
        except Exception:pass
