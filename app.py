"""Point Pattern Studio / 點分布分析與點畫最佳化工具 (PyQt6 / PySide6)."""
from __future__ import annotations

import json
import math
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

try:
    from PyQt6.QtCore import Qt, QThread, pyqtSignal as Signal
    from PyQt6.QtGui import QPixmap, QFont
    from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QTabWidget, QHBoxLayout,
        QVBoxLayout, QGridLayout, QLabel, QPushButton, QSpinBox, QDoubleSpinBox,
        QLineEdit, QComboBox, QFileDialog, QTableWidget, QTableWidgetItem,
        QHeaderView, QGroupBox, QProgressBar, QSplitter, QMessageBox, QCheckBox,
        QScrollArea, QAbstractItemView, QFrame, QMenu)
except ImportError:
    from PySide6.QtCore import Qt, QThread, Signal
    from PySide6.QtGui import QPixmap, QFont
    from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QTabWidget, QHBoxLayout,
        QVBoxLayout, QGridLayout, QLabel, QPushButton, QSpinBox, QDoubleSpinBox,
        QLineEdit, QComboBox, QFileDialog, QTableWidget, QTableWidgetItem,
        QHeaderView, QGroupBox, QProgressBar, QSplitter, QMessageBox, QCheckBox,
        QScrollArea, QAbstractItemView, QFrame, QMenu)

from point_core import (analyze, random_pattern, render_points, extract_dots,
    load_points_data, save_points_csv, save_metrics_csv, image_skeleton,
    evenly_sample_strokes, optimize_pattern, load_image, canvas_size, draw_points,
    PATTERN_LABELS, PATTERN_LABELS_EN, HYBRID_KINDS)
from plots import l_analysis, plot_title, save_l_curves_csv
from presets import PRESETS, make_preset, preset_filename

BASE=Path(__file__).resolve().parent
OUTPUT=BASE/'output'
OUTPUT.mkdir(exist_ok=True)

MODE_LABELS={'各種模式隨機混合':'surprise','完全隨機 (CSR)':'random',
             '群聚 (Cluster)':'cluster','規律 (Regular)':'regular',
             f'混合 (Hybrid)：下列 {len(HYBRID_KINDS)} 種隨機':'hybrid_any'}
MODE_LABELS.update({'　└ '+PATTERN_LABELS[k]:k for k in HYBRID_KINDS})

METRIC_INFO={
    'score':'總評分 −1 群聚 / 0 隨機 / +1 規律',
    'hopkins_h':'Hopkins H；越大越群聚',
    'hopkins_component':'Hopkins 對稱有界分數',
    'ripley_index':'多尺度 Ripley 正規化 (r−L)/r 平均；越大越均勻',
    'ripley_component':'Ripley tanh 有界分數',
    'nni':'Clark–Evans 最近鄰指數；CSR 約 1（未做邊界修正）',
    'nni_edge_corrected':'Clark–Evans 最近鄰指數，Donnelly 邊界修正；CSR 約 1',
    'nn_mean':'最近鄰距離平均（寬高比校正空間）',
    'nn_std':'最近鄰距離標準差',
    'nn_cv':'最近鄰距離變異係數',
    'voronoi_area_cv':'Voronoi 面積 CV（網格近似，解析度見 voronoi_resolution）',
    'structure_factor_low_k':'低頻 Structure Factor；群聚偏高，規律偏低',
    'spectral_peak_ratio':'Fourier 頻譜尖峰比；有週期結構時偏高',
    'spectral_anisotropy':'Fourier 頻譜方向異向性',
    'x_mean':'X 座標平均（0–1）',
    'y_mean':'Y 座標平均（0–1）',
    'x_std':'X 座標標準差',
    'y_std':'Y 座標標準差',
    'x_var':'X 座標變異數（母體定義）',
    'y_var':'Y 座標變異數（母體定義）',
    'pattern_type':'產生方式（英文代碼；ms_小尺度_大尺度）',
    'pattern_label':'產生方式',
    'lr_plot':'L(r) 圖檔名；虛線 L(r)=r 為完全隨機',
    'lr_clustered_r':'L(r) 高於隨機模擬範圍的 r 區間＝在這些尺度顯著群聚（none＝沒有）',
    'lr_regular_r':'L(r) 低於隨機模擬範圍的 r 區間＝在這些尺度顯著均勻（none＝沒有）',
    'lr_max_L_minus_r':'L(r)−r 最大值（正＝群聚程度）',
    'lr_r_at_max':'L(r)−r 最大值出現的 r',
    'lr_min_L_minus_r':'L(r)−r 最小值（負＝均勻程度）',
    'lr_r_at_min':'L(r)−r 最小值出現的 r',
    'lr_r_max':'L(r) 計算到的最大 r（畫布高度 = 1）',
}
L_SUMMARY_KEYS=['lr_clustered_r','lr_regular_r','lr_max_L_minus_r','lr_r_at_max',
                'lr_min_L_minus_r','lr_r_at_min','lr_r_max']


def l_summary_text(stats):
    """One line for the status bar: at which scales the L(r) curve leaves the random band."""
    cl,rg=stats.get('lr_clustered_r','none'),stats.get('lr_regular_r','none')
    parts=([f'r = {cl} 顯著群聚'] if cl!='none' else [])+([f'r = {rg} 顯著均勻'] if rg!='none' else [])
    return 'L(r)：'+('；'.join(parts) if parts else '全程在隨機模擬範圍內')


def valstr(value):
    if isinstance(value,(int,np.integer)):return str(value)
    if isinstance(value,(float,np.floating)):
        if not math.isfinite(value): return '—'
        return f'{value:.6f}' if abs(value)>=.0001 or value==0 else f'{value:.3e}'
    return str(value)


def make_spin(lo,hi,value,step=1):
    x=QSpinBox();x.setRange(lo,hi);x.setValue(value);x.setSingleStep(step)
    return x


def make_double(lo,hi,value,step=.01,decimals=3):
    x=QDoubleSpinBox();x.setRange(lo,hi);x.setValue(value);x.setSingleStep(step)
    x.setDecimals(decimals)
    return x


def add_field(layout, label, widget, row, col=0):
    title=QLabel(label);title.setWordWrap(True)
    layout.addWidget(title,row,col); layout.addWidget(widget,row,col+1)


def choose_file(widget, filters):
    path,_=QFileDialog.getOpenFileName(widget,'開啟檔案',str(BASE),filters)
    return path


def choose_folder(widget):
    return QFileDialog.getExistingDirectory(widget,'選擇輸出資料夾',str(OUTPUT))


def directory(prefix):
    name=datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    p=OUTPUT/(prefix+'_'+name)
    p.mkdir(parents=True,exist_ok=False)
    return p


def png_pixmap(data):
    pix=QPixmap(); pix.loadFromData(bytes(data),'PNG')
    return pix


def point_preview(points, aspect=1., base_image=None, long_side=800):
    """QPixmap of the dots, black on white, at the same size and dot style as the
    exported PNG (so 'copy image' gives exactly what export would save)."""
    w,h = canvas_size(aspect,long_side)
    if base_image is None:
        canvas=draw_points(points,(w,h),3)
    else:
        raw=load_image(base_image,'RGB')
        raw=cv2.resize(raw,(w,h),interpolation=cv2.INTER_AREA)
        canvas=(.18*raw+.82*np.full_like(raw,255)).astype(np.uint8)
        for x,y in points:
            cv2.circle(canvas,(int(round(x*(w-1))),int(round(y*(h-1)))),3,(18,18,18),-1,cv2.LINE_AA)
    # Qt's image loader handles PNG byte arrays regardless of Qt binding.
    ok,buf=cv2.imencode('.png',cv2.cvtColor(canvas,cv2.COLOR_RGB2BGR))
    if not ok:raise ValueError('繪圖失敗')
    return png_pixmap(buf)


def set_picture(label, pix, name=None):
    """Show a picture (file path, PNG bytes or QPixmap); the full-size original is kept
    for the right-click copy / save menu."""
    if isinstance(pix,(str,Path)):
        name=name or Path(pix).name
        pix=QPixmap(str(pix))
    elif isinstance(pix,(bytes,bytearray)):
        pix=png_pixmap(pix)
    if pix.isNull():return
    label.setProperty('source_pixmap',pix)
    label.setProperty('source_name',name or '')
    apply_picture(label)


def apply_picture(label):
    pix=label.property('source_pixmap')
    if isinstance(pix,QPixmap) and not pix.isNull():
        label.setPixmap(pix.scaled(max(150,label.width()-8),max(150,label.height()-8),
            Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))


class PictureLabel(QLabel):
    """Picture panel. Right-click: copy the full-size picture to the clipboard, or save it."""
    def __init__(self, caption='預覽', default_name='image.png', min_side=240):
        super().__init__(caption)
        self.default_name=default_name
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(min_side,min_side)
        self.setToolTip('滑鼠右鍵：複製圖片到剪貼簿／另存圖片')
        self.setStyleSheet('background:#ffffff; border:1px solid #dce3e9; border-radius:9px; color:#81909c;')
    def resizeEvent(self,event):
        super().resizeEvent(event)
        apply_picture(self)
    def picture(self):
        pix=self.property('source_pixmap')
        return pix if isinstance(pix,QPixmap) and not pix.isNull() else None
    def copy_picture(self):
        pix=self.picture()
        if pix is not None:
            QApplication.clipboard().setImage(pix.toImage())
    def save_picture(self):
        pix=self.picture()
        if pix is None:return
        name=self.property('source_name') or self.default_name
        path,_=QFileDialog.getSaveFileName(self,'另存圖片',str(OUTPUT/Path(name).with_suffix('.png').name),
                                           'PNG 圖片 (*.png)')
        if path:
            if not path.lower().endswith('.png'):path+='.png'
            if not pix.save(path,'PNG'):
                QMessageBox.warning(self,'儲存失敗','無法寫入：'+path)
    def contextMenuEvent(self,event):
        if self.picture() is None:return
        menu=QMenu(self)
        copy=menu.addAction('複製圖片'); copy.triggered.connect(self.copy_picture)
        save=menu.addAction('另存圖片…'); save.triggered.connect(self.save_picture)
        menu.exec(event.globalPos())


class TaskThread(QThread):
    progress=Signal(int,str)
    success=Signal(object)
    failure=Signal(str,str)
    def __init__(self,fn):
        super().__init__();self.fn=fn;self.cancel_requested=False
    def run(self):
        try:
            result=self.fn(lambda pct,msg: self.progress.emit(int(pct),str(msg)),
                            lambda: self.cancel_requested)
            self.success.emit(result)
        except Exception as exc:
            self.failure.emit(str(exc) or type(exc).__name__, traceback.format_exc())


def show_error(parent, message, details=''):
    """Short readable message first; the full traceback is under 'Show Details'."""
    box=QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Critical)
    box.setWindowTitle('錯誤')
    box.setText(message)
    if details:
        box.setDetailedText(details[-8000:])
    box.exec()


class MetricsPanel(QTableWidget):
    def __init__(self):
        super().__init__(0,3)
        self.setHorizontalHeaderLabels(['項目','數值','意義／計算方式'])
        self.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeMode.Stretch)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)
    def show_metrics(self, metrics):
        if metrics is None: self.setRowCount(0);return
        ordered=['score','n_points','pattern_label','hopkins_h','hopkins_component','ripley_index',
                 'ripley_component',*L_SUMMARY_KEYS,'nni','nn_mean','nn_std','nn_cv','voronoi_area_cv','quadrat_vmr_4x4',
                 'quadrat_vmr_8x8','quadrat_vmr_12x12','structure_factor_low_k',
                 'spectral_peak_ratio','spectral_anisotropy','x_mean','y_mean','x_std',
                 'y_std','x_var','y_var']
        keys=list(dict.fromkeys([k for k in ordered if k in metrics]+list(metrics.keys())))
        self.setRowCount(len(keys))
        for r,k in enumerate(keys):
            val=valstr(metrics[k]);desc=METRIC_INFO.get(k,'')
            for c,t in enumerate((k,val,desc)):
                item=QTableWidgetItem(t)
                if c==1:item.setTextAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter)
                self.setItem(r,c,item)


class BaseTab(QWidget):
    def __init__(self):
        super().__init__();self.job=None
        self.status=QLabel('就緒')
        self.status.setWordWrap(True)
        self.progress=QProgressBar();self.progress.setValue(0)
    def busy(self, fn, done):
        if self.job and self.job.isRunning():
            QMessageBox.information(self,'執行中','請先完成或停止目前任務。');return
        self.job=TaskThread(fn)
        self.job.progress.connect(lambda val,msg:(self.progress.setValue(val),self.status.setText(msg)))
        self.job.success.connect(done)
        self.job.failure.connect(lambda msg,txt:(self.status.setText('執行失敗：'+msg),
                                                 show_error(self,msg,txt)))
        self.job.finished.connect(lambda:self.progress.setValue(100) if self.job and not self.job.cancel_requested else None)
        self.job.start()
    def footer(self,layout):
        box=QHBoxLayout();box.addWidget(self.progress,1);box.addWidget(self.status,3)
        stop=QPushButton('停止');stop.setObjectName('secondary')
        stop.clicked.connect(lambda: setattr(self.job,'cancel_requested',True) if self.job else None)
        box.addWidget(stop)
        layout.addLayout(box)


def picture_pair(left, right, below, sizes=(430,360)):
    """Two pictures side by side above a metrics table (user-resizable)."""
    split=QSplitter(Qt.Orientation.Vertical)
    pics=QWidget(); row=QHBoxLayout(pics); row.setContentsMargins(0,0,0,0)
    row.addWidget(left,1); row.addWidget(right,1)
    split.addWidget(pics); split.addWidget(below); split.setSizes(list(sizes))
    return split


class BatchTab(BaseTab):
    def __init__(self):
        super().__init__();self.rows=[];self.image_paths=[];self.lplot_paths=[]
        outer=QVBoxLayout(self)
        group=QGroupBox('產生參數');grid=QGridLayout(group)
        self.nimgs=make_spin(1,2000,12)
        self.npts=make_spin(3,10000,180)
        self.mode=QComboBox();self.mode.addItems(MODE_LABELS.keys())
        self.mode.setMaxVisibleItems(len(MODE_LABELS))
        self.strength=make_double(0,1,.75,.05,2)
        self.random_strength=QCheckBox('每張隨機強度');self.random_strength.setChecked(True)
        self.width=make_spin(128,2400,800,100)
        self.height=make_spin(128,2400,800,100)
        self.seed=make_spin(0,999999999,2026)
        add_field(grid,'生成張數 N',self.nimgs,0,0)
        add_field(grid,'每張點數',self.npts,0,2)
        add_field(grid,'分布模式',self.mode,1,0)
        add_field(grid,'強度 (0–1)',self.strength,1,2)
        add_field(grid,'畫布寬度 (px)',self.width,2,0)
        add_field(grid,'畫布高度 (px)',self.height,2,2)
        add_field(grid,'亂數種子',self.seed,3,0)
        grid.addWidget(self.random_strength,3,2,1,2)
        self.run=QPushButton('產生 N 張並計算全部指標')
        self.run.clicked.connect(self.generate)
        grid.addWidget(self.run,4,0,1,4)
        outer.addWidget(group)
        splitter=QSplitter(Qt.Orientation.Horizontal)
        left=QWidget(); ll=QVBoxLayout(left)
        self.table=QTableWidget(0,8)
        self.table.setHorizontalHeaderLabels(['編號','類別','分數','H','Ripley','NNI','X 平均','Y 平均'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.itemSelectionChanged.connect(self.pick)
        ll.addWidget(self.table)
        splitter.addWidget(left)
        self.preview=PictureLabel('點選左側表格查看點圖')
        self.lplot=PictureLabel('L(r) 圖')
        self.details=MetricsPanel()
        splitter.addWidget(picture_pair(self.preview,self.lplot,self.details))
        splitter.setSizes([560,840])
        outer.addWidget(splitter,1)
        self.footer(outer)
    def generate(self):
        n,points=self.nimgs.value(),self.npts.value()
        mode=MODE_LABELS[self.mode.currentText()]
        intensity=self.strength.value();randstrength=self.random_strength.isChecked()
        w,h=self.width.value(),self.height.value()
        seed=self.seed.value()
        if n*points>1200000:
            if QMessageBox.question(self,'產量較大','生成很多點可能需要較長時間，確定繼續嗎？')!=QMessageBox.StandardButton.Yes:
                return
        def job(progress,cancelled):
            root=directory('batch')
            rows=[];paths=[];lpaths=[];curves=[]
            rng=np.random.default_rng(seed)
            aspect=w/h
            progress(0,'產生中...')
            for i in range(n):
                if cancelled():break
                variation=float(rng.uniform(.30,.98)) if randstrength else intensity
                pp,typ=random_pattern(points,mode,variation,rng,aspect=aspect)
                # Default probe seed: the same points get the same score in every tab and in the CLI.
                stats=analyze(pp,aspect=aspect)
                name=f'pattern_{i+1:04d}'
                img=root/f'{name}.png'
                render_points(pp,img,(w,h),dot_radius=max(2,int(min(w,h)*.004)))
                save_points_csv(root/f'{name}_xy.csv',pp)
                lplot=root/f'{name}_Lr.png'
                curve,envelope,summary,_=l_analysis(pp,aspect,plot_title(PATTERN_LABELS_EN[typ],stats['score']),lplot)
                curves.append((name,curve,envelope))
                stats.update(summary)
                stats.update(id=f'{i+1:04d}',pattern_type=typ,pattern_label=PATTERN_LABELS[typ],
                             strength=variation,image=str(img.name),point_file=f'{name}_xy.csv',
                             lr_plot=lplot.name)
                rows.append(stats);paths.append(str(img));lpaths.append(str(lplot))
                progress((i+1)*100/n,f'已產生 {i+1} / {n} 張｜輸出：{root}')
            save_metrics_csv(root/'all_metrics.csv',rows)
            save_l_curves_csv(root/'Lr_curves.csv',curves)
            return {'rows':rows,'paths':paths,'lpaths':lpaths,'root':str(root)}
        self.status.setText('正在產生...')
        self.busy(job,self.done)
    def done(self,result):
        self.rows=result['rows']; self.image_paths=result['paths']; self.lplot_paths=result['lpaths']
        self.table.setRowCount(len(self.rows))
        for i,r in enumerate(self.rows):
            vals=[r['id'],r['pattern_label'],f"{r['score']:+.4f}",f"{r['hopkins_h']:.4f}",
                  f"{r['ripley_index']:+.4f}",f"{r['nni']:.3f}",f"{r['x_mean']:.3f}",f"{r['y_mean']:.3f}"]
            for j,v in enumerate(vals):self.table.setItem(i,j,QTableWidgetItem(str(v)))
        self.table.resizeColumnsToContents()
        if self.rows:self.table.selectRow(0)
        self.status.setText(f"完成 {len(self.rows)} 張；點圖與 L(r) 圖 PNG、座標 CSV、完整指標已存至：{result['root']}"
                            '（圖片可按右鍵複製）')
    def pick(self):
        idx=self.table.currentRow()
        if idx<0 or idx>=len(self.rows):return
        set_picture(self.preview,self.image_paths[idx])
        set_picture(self.lplot,self.lplot_paths[idx])
        self.details.show_metrics(self.rows[idx])


class ImportTab(BaseTab):
    def __init__(self):
        super().__init__();self.current_points=None;self.current_stats=None;self.current_aspect=1.
        outer=QVBoxLayout(self)
        group=QGroupBox('匯入白底黑點圖，或 x,y 座標 CSV / TXT / JSON')
        g=QGridLayout(group)
        self.file=QLineEdit();self.file.setPlaceholderText('選擇 PNG / JPG / BMP / TIFF / CSV / TXT / JSON')
        btn=QPushButton('選擇檔案');btn.setObjectName('secondary');btn.clicked.connect(self.browse)
        g.addWidget(QLabel('匯入檔案'),0,0);g.addWidget(self.file,0,1,1,4);g.addWidget(btn,0,5)
        self.threshold=make_spin(1,254,140)
        self.minarea=make_spin(1,999999,5)
        self.invert=QCheckBox('白點黑底（反轉）')
        add_field(g,'圖片黑點閾值',self.threshold,1,0)
        add_field(g,'連通區最小面積(px²)',self.minarea,1,2)
        g.addWidget(self.invert,1,4,1,2)
        self.width=make_double(1,1000000,800,100,1)
        self.height=make_double(1,1000000,800,100,1)
        self.bbox=QCheckBox('資料依自身邊界縮放至 0–1（改變評分，請慎用）')
        add_field(g,'座標資料畫布寬度',self.width,2,0)
        add_field(g,'座標資料畫布高度',self.height,2,2)
        g.addWidget(self.bbox,3,0,1,6)
        run=QPushButton('分析目前圖片／座標');run.clicked.connect(self.compute)
        out=QPushButton('匯出分析 CSV 與點座標');out.setObjectName('secondary');out.clicked.connect(self.export)
        g.addWidget(run,4,0,1,3);g.addWidget(out,4,3,1,3)
        outer.addWidget(group)
        self.preview=PictureLabel('匯入後顯示圖形')
        self.lplot=PictureLabel('L(r) 圖','analysed_Lr.png')
        self.metrics=MetricsPanel()
        outer.addWidget(picture_pair(self.preview,self.lplot,self.metrics,(470,330)),1)
        self.footer(outer)
    def browse(self):
        p=choose_file(self,'影像 / 點座標 (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.csv *.txt *.json);;所有檔案 (*)')
        if p:self.file.setText(p)
    def compute(self):
        path=self.file.text().strip()
        if not Path(path).is_file():
            QMessageBox.warning(self,'找不到檔案','請選擇存在的檔案。');return
        threshold=self.threshold.value();area=self.minarea.value();inv=self.invert.isChecked()
        width=self.width.value();height=self.height.value();bbox=self.bbox.isChecked()
        def task(progress,cancelled):
            ext=Path(path).suffix.lower()
            if ext in ('.png','.jpg','.jpeg','.bmp','.tif','.tiff'):
                points,aspect,meta=extract_dots(path,threshold,area,inv)
                source='image'
            else:
                points,aspect=load_points_data(path,width,height,bbox)
                meta={};source='data'
            progress(30,f'偵測 {len(points)} 點，計算全部統計量...')
            stats=analyze(points,aspect)
            progress(60,'計算 L(r) 與完全隨機模擬範圍...')
            curve,envelope,summary,lpng=l_analysis(points,aspect,plot_title(Path(path).name,stats['score']))
            stats.update(summary)
            return dict(points=points,stats=stats,aspect=aspect,meta=meta,source=source,path=path,
                        curve=curve,envelope=envelope,lpng=lpng)
        self.busy(task,self.done)
    def done(self,result):
        self.current_points=result['points'];self.current_stats=result['stats']
        self.current_aspect=result['aspect']
        self.current_curve=result['curve'];self.current_envelope=result['envelope']
        self.current_lpng=result['lpng'];self.current_name=Path(result['path']).name
        self.metrics.show_metrics(self.current_stats)
        if result['source']=='image':set_picture(self.preview,result['path'])
        else:set_picture(self.preview,point_preview(self.current_points,self.current_aspect),
                         Path(result['path']).stem+'_points.png')
        set_picture(self.lplot,self.current_lpng,Path(result['path']).stem+'_Lr.png')
        warning=result['meta'].get('warning','')
        self.status.setText(f"分析 {len(self.current_points)} 點，分數 {self.current_stats['score']:+.4f}。"
                            f"{l_summary_text(self.current_stats)}。{warning}")
    def export(self):
        if self.current_points is None:
            QMessageBox.information(self,'無資料','請先分析一份資料。');return
        folder=QFileDialog.getExistingDirectory(self,'選擇匯出位置',str(OUTPUT))
        if not folder:return
        save_points_csv(Path(folder)/'analysed_xy.csv',self.current_points)
        save_metrics_csv(Path(folder)/'analysed_metrics.csv',[self.current_stats])
        render_points(self.current_points,Path(folder)/'analysed_points.png',canvas_size(self.current_aspect))
        (Path(folder)/'analysed_Lr.png').write_bytes(self.current_lpng)
        save_l_curves_csv(Path(folder)/'analysed_Lr_curve.csv',
                          [(self.current_name,self.current_curve,self.current_envelope)])
        self.status.setText('已匯出 '+str(folder))


class OptimizeTab(BaseTab):
    def __init__(self):
        super().__init__()
        self.original_points=None;self.result=None;self.current_stats=None
        outer=QVBoxLayout(self)
        group=QGroupBox('線條圖 → 均勻在線上放點 → 最小位移啟發式搜尋')
        grid=QGridLayout(group)
        self.file=QLineEdit();self.file.setPlaceholderText('可匯入人臉、魚、手繪線條圖；優先使用黑線白底（透明背景 PNG 亦可）')
        browse=QPushButton('上傳線條圖');browse.clicked.connect(self.browse);browse.setObjectName('secondary')
        self.example=QComboBox();self.example.addItems(list(PRESETS))
        self.example.setMaxVisibleItems(len(PRESETS))
        sample=QPushButton('載入內建示範');sample.clicked.connect(self.example_load);sample.setObjectName('secondary')
        grid.addWidget(QLabel('圖像'),0,0);grid.addWidget(self.file,0,1,1,3)
        grid.addWidget(browse,0,4);grid.addWidget(self.example,0,5);grid.addWidget(sample,0,6)
        self.npts=make_spin(3,10000,180)
        self.target=make_double(-1,1,-.13,.01,3)
        self.tolerance=make_double(.001,.25,.035,.005,3)
        self.iterations=make_spin(50,50000,3600,250)
        self.threshold=make_spin(1,254,150)
        self.invert=QCheckBox('白線黑底')
        self.max_off=make_double(.005,.8,.09,.01,3)
        self.no_limit=QCheckBox('允許離線移動不限距離（可能破壞原圖）')
        self.retention=make_double(0,1,.65,.05,2)
        self.seed=make_spin(0,999999999,2026)
        add_field(grid,'點數',self.npts,1,0)
        add_field(grid,'目標 PPDI',self.target,1,2)
        add_field(grid,'允許誤差 ±',self.tolerance,1,4)
        add_field(grid,'最佳化迭代數',self.iterations,2,0)
        add_field(grid,'線條黑色閾值',self.threshold,2,2)
        add_field(grid,'最大離線距離（依高度）',self.max_off,2,4)
        grid.addWidget(self.invert,3,0,1,2)
        grid.addWidget(self.no_limit,3,2,1,4)
        add_field(grid,'亂數種子',self.seed,4,0)
        add_field(grid,'最低線條保留率',self.retention,4,2)
        self.prep=QPushButton('① 解析線條並放置初始點')
        self.prep.clicked.connect(self.prepare)
        self.go=QPushButton('② 微調位置逼近目標分數')
        self.go.clicked.connect(self.optimize)
        self.go.setEnabled(False)
        self.save=QPushButton('③ 匯出點圖／座標／完整分析')
        self.save.clicked.connect(self.export)
        self.save.setObjectName('secondary');self.save.setEnabled(False)
        grid.addWidget(self.prep,5,0,1,2)
        grid.addWidget(self.go,5,2,1,3)
        grid.addWidget(self.save,5,5,1,2)
        outer.addWidget(group)
        # One row of five panels (not two rows) so the tab still fits a 1280x720 screen.
        picrow=QHBoxLayout()
        self.source_preview=PictureLabel('原始線條',min_side=170)
        self.before_preview=PictureLabel('起始點分布','before_points.png',170)
        self.after_preview=PictureLabel('最佳化後點分布','optimized_points.png',170)
        self.before_lplot=PictureLabel('起始點的 L(r) 圖','before_Lr.png',170)
        self.after_lplot=PictureLabel('最佳化後的 L(r) 圖','optimized_Lr.png',170)
        for label,title in [(self.source_preview,'原始線條圖'),(self.before_preview,'起始點分布'),
                            (self.after_preview,'目標點分布'),(self.before_lplot,'起始點 L(r)'),
                            (self.after_lplot,'目標點 L(r)')]:
            col=QVBoxLayout();col.addWidget(QLabel(title));col.addWidget(label,1)
            picrow.addLayout(col,1)
        outer.addLayout(picrow,2)
        splitter=QSplitter(Qt.Orientation.Horizontal)
        self.summary=QLabel('評分與保形性統計將顯示於此。')
        self.summary.setWordWrap(True)
        self.summary.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.summary.setStyleSheet('background:#edf4f8; border-radius:7px; padding:14px;')
        # Scrollable, so the long summary never forces the window taller than a 720-px screen.
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(self.summary)
        splitter.addWidget(scroll)
        self.metrics=MetricsPanel()
        splitter.addWidget(self.metrics)
        splitter.setSizes([520,750])
        outer.addWidget(splitter,1)
        self.footer(outer)
    def example_load(self):
        label=self.example.currentText()
        path=BASE/'samples'/preset_filename(label)
        make_preset(label,path)
        self.file.setText(str(path))
        set_picture(self.source_preview,str(path))
        self.go.setEnabled(False);self.save.setEnabled(False)
    def browse(self):
        p=choose_file(self,'線條圖片 (*.png *.jpg *.jpeg *.bmp *.tif *.tiff)')
        if p:
            self.file.setText(p);set_picture(self.source_preview,p)
            self.go.setEnabled(False);self.save.setEnabled(False)
    def prepare(self):
        path=self.file.text().strip()
        if not Path(path).is_file():
            QMessageBox.warning(self,'尚未指定線條圖','請上傳線條圖或載入內建示範。');return
        threshold=self.threshold.value();invert=self.invert.isChecked()
        npts=self.npts.value();seed=self.seed.value()
        def job(progress,cancelled):
            progress(5,'解析線條骨架...')
            stroke,aspect,meta=image_skeleton(path,threshold,invert)
            progress(35,f'沿線條放置 {npts} 個點...')
            p=evenly_sample_strokes(stroke,npts,aspect=aspect,seed=seed)
            progress(80,'計算統計量...')
            stats=analyze(p,aspect)
            progress(90,'計算 L(r) 與完全隨機模擬範圍...')
            curve,envelope,summary,png=l_analysis(p,aspect,plot_title(f'{Path(path).stem}: starting dots',stats['score']))
            stats.update(summary)
            return dict(stroke=stroke,aspect=aspect,meta=meta,points=p,stats=stats,path=path,
                        lr=(curve,envelope,png))
        self.go.setEnabled(False);self.save.setEnabled(False)
        self.busy(job,self.prepared)
    def prepared(self,r):
        p,stats,meta=r['points'],r['stats'],r['meta']
        self.stroke=r['stroke'];self.aspect=r['aspect'];self.original_points=p
        self.current_stats=stats;self.result=None
        self.source_path=r['path'];self.lr_before=r['lr'];self.lr_after=None
        set_picture(self.before_preview,point_preview(p,self.aspect))
        set_picture(self.after_preview,point_preview(p,self.aspect))
        # Until ② runs, the "target" panels show the starting dots, as before.
        set_picture(self.before_lplot,self.lr_before[2])
        set_picture(self.after_lplot,self.lr_before[2])
        self.metrics.show_metrics(stats)
        self.summary.setText(f"初始點數：{len(p)}\n起始分數：{stats['score']:+.4f}\n"
            f"Hopkins H：{stats['hopkins_h']:.4f}\nRipley：{stats['ripley_index']:+.4f}\n"
            f"{l_summary_text(stats)}\n"
            f"線條骨架像素數：{meta['skeleton_pixels']}\n"
            '請按 ② 開始最佳化。分數越接近 0 不代表越像原圖；請檢查輪廓保留率。')
        self.go.setEnabled(True);self.save.setEnabled(False)
        self.status.setText(f"已在圖上放入 {len(p)} 個點，初始分數 {stats['score']:+.4f}。")
    def optimize(self):
        if self.original_points is None:
            QMessageBox.warning(self,'請先放點','先按 ① 放置初始點。');return
        p=self.original_points.copy();stroke=self.stroke.copy();aspect=self.aspect
        target=self.target.value();iters=self.iterations.value();tol=self.tolerance.value()
        maxdist=None if self.no_limit.isChecked() else self.max_off.value()
        seed=self.seed.value();retention=self.retention.value()
        name=Path(self.source_path).stem
        start_lr={k:v for k,v in self.current_stats.items() if k.startswith('lr_')}
        def job(progress,cancelled):
            def report(i,n,sc,achieved):
                progress(100*i/n,f"搜尋 {i}/{n}｜目前最佳 {sc:+.4f}｜"
                         +('已達誤差門檻' if achieved else '尚未達標'))
            result=optimize_pattern(p,target,aspect,stroke,iterations=iters,tolerance=tol,
                   max_stroke_distance=maxdist,min_stroke_retention=retention,
                   seed=seed,progress=report,cancellation=cancelled)
            # Optimizer and analyze() share the default Hopkins probes, so these
            # are the same scores tab ② gives when the exported CSV is re-imported.
            result['initial_stats']=analyze(p,aspect)
            result['initial_stats'].update(start_lr)
            result['final_stats']=analyze(result['points'],aspect)
            progress(100,'計算最佳化後的 L(r)...')
            curve,envelope,summary,png=l_analysis(result['points'],aspect,plot_title(
                f'{name}: optimized (target {target:+.2f})',result['final_stats']['score']))
            result['final_stats'].update(summary)
            result['_lr_after']=(curve,envelope,png)    # kept out of the JSON report
            result['settings']=dict(source=Path(self.source_path).name,n_points=len(p),aspect=aspect,
                                    max_stroke_distance=maxdist,min_stroke_retention=retention,
                                    iterations_requested=iters,search_seed=seed)
            return result
        self.busy(job,self.optimized)
    def optimized(self,result):
        self.lr_after=result.pop('_lr_after')
        self.result=result;self.save.setEnabled(True)
        set_picture(self.after_preview,point_preview(result['points'],self.aspect))
        set_picture(self.after_lplot,self.lr_after[2])
        full=result['final_stats']
        self.metrics.show_metrics(full)
        tol=result['tolerance']
        diff=abs(full['score']-result['target'])
        reached_full=diff<=tol
        info='達標' if reached_full else '未達標（保形限制／分布條件可能不相容）'
        hint=''
        if not reached_full and result['settings']['max_stroke_distance'] is not None:
            hint=('\n提示：線條圖的點只在線附近時，整張畫布統計上必然偏群聚。'
                  '可提高「最大離線距離」、勾選「允許離線移動不限距離」，或降低「最低線條保留率」。\n')
        self.summary.setText(
            f"搜尋結果：{info}\n{hint}\n目標：{result['target']:+.4f} ± {tol:.3f}\n"
            f"起始分數（完整分析）：{result['initial_stats']['score']:+.4f}\n"
            f"最終分數（完整分析）：{full['score']:+.4f}\n"
            f"與目標差距：{diff:.4f}\n"
            f"起始 {l_summary_text(result['initial_stats'])}\n"
            f"最佳化後 {l_summary_text(full)}\n\n"
            f"全部點總位移（幾何單位）：{result['total_movement']:.4f}\n"
            f"平均每點位移：{result['mean_movement']:.4f}\n"
            f"最大單點位移：{result['max_movement']:.4f}\n"
            f"最終位於線條附近（距離 0.025 內）：{result['retained_within_025']:.1%}\n"
            f"迭代數：{result['iterations']}\n\n"
            '注意：此為近似最小位移啟發式演算法，不保證全域最佳解。')
        self.status.setText(f"{info}；完成評分 {full['score']:+.4f}，可按 ③ 匯出。")
    def export(self):
        if self.result is None:return
        folder=QFileDialog.getExistingDirectory(self,'選擇儲存位置',str(OUTPUT))
        if not folder:return
        folder=Path(folder)
        original=self.original_points
        final=self.result['points']
        size=canvas_size(self.aspect)
        render_points(original,folder/'before_points.png',size)
        render_points(final,folder/'optimized_points.png',size)
        save_points_csv(folder/'before_xy.csv',original)
        save_points_csv(folder/'optimized_xy.csv',final)
        stats_before={'phase':'before',**self.result['initial_stats']}
        stats_after={'phase':'after',**self.result['final_stats']}
        save_metrics_csv(folder/'before_after_metrics.csv',[stats_before,stats_after])
        (folder/'before_Lr.png').write_bytes(self.lr_before[2])
        (folder/'optimized_Lr.png').write_bytes(self.lr_after[2])
        save_l_curves_csv(folder/'Lr_curves.csv',[('before',*self.lr_before[:2]),
                                                   ('optimized',*self.lr_after[:2])])
        # Use faint underlying strokes in overlay to visually audit shape preservation.
        base=load_image(self.source_path,'RGB').astype(float)
        h,w=base.shape[:2]
        faded=(.18*base+.82*255).astype('uint8')
        for x,y in final:
            cv2.circle(faded,(int(round(x*(w-1))),int(round(y*(h-1)))),max(2,int(min(w,h)*.004)),(7,54,200),-1,cv2.LINE_AA)
        Image.fromarray(faded).save(folder/'optimized_overlay.png')
        metadata={key:val for key,val in self.result.items() if key not in ('points','initial_stats','final_stats')}
        metadata['score_full_report']=self.result['final_stats']['score']
        (folder/'optimization_report.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
        self.status.setText(f'匯出完成：{folder}')


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Point Pattern Studio — 點分布評分與圖形點化')
        self.resize(1450,950)
        self.tabs=QTabWidget()
        self.tabs.addTab(BatchTab(),'① 批次生成點圖')
        self.tabs.addTab(ImportTab(),'② 匯入圖片／座標分析')
        self.tabs.addTab(OptimizeTab(),'③ 線條圖 → 指定評分')
        self.setCentralWidget(self.tabs)
        self.setStyleSheet('''
            QMainWindow, QWidget {background:#f7fafc; color:#192a36; font-size:12px;}
            QGroupBox {background:#ffffff; border:1px solid #dde6ee; border-radius:10px;
                       margin-top:13px; padding:13px; font-weight:600;}
            QGroupBox::title {subcontrol-origin:margin; left:12px; padding:0 5px;}
            QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {background:#fff; border:1px solid #cbd9e3;
                border-radius:5px; padding:5px; min-height:20px;}
            QPushButton {background:#146c88; color:#fff; border:none; border-radius:7px;
                padding:9px 14px; font-weight:600;}
            QPushButton:hover {background:#0b5369;}
            QPushButton:disabled {background:#a5bec7; color:#f1f3f5;}
            QPushButton#secondary {background:#e8f2f6; color:#18546b;}
            QPushButton#secondary:hover {background:#d7e8ee;}
            QTabWidget::pane {border:1px solid #d8e4ee; background:#f7fafc;}
            QTabBar::tab {background:#e9eef4; padding:12px 20px; margin-right:3px;}
            QTabBar::tab:selected {background:white; color:#146c88; font-weight:700;}
            QTableWidget {background:#fff; alternate-background-color:#f4f9fc;
                gridline-color:#e5edf1; selection-background-color:#d0eaf2;}
            QHeaderView::section {background:#e9f2f7; padding:7px; border:0; font-weight:600;}
            QProgressBar {background:#e5eef2; border:0; border-radius:5px; height:16px;}
            QProgressBar::chunk {background:#3c94aa; border-radius:5px;}
        ''')
    def closeEvent(self,event):
        running=[t.job for t in (self.tabs.widget(i) for i in range(self.tabs.count()))
                 if t.job and t.job.isRunning()]
        if running:
            QMessageBox.warning(self,'工作進行中','請按「停止」，等運算結束後再關閉。')
            event.ignore()
        else: event.accept()


def main():
    app=QApplication(sys.argv)
    app.setApplicationName('Point Pattern Studio')
    app.setFont(QFont('Microsoft JhengHei',10))
    window=MainWindow();window.show()
    return app.exec()


if __name__=='__main__':
    sys.exit(main())
