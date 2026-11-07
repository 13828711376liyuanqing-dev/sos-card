"""SAM | 2026-10-21 +08:00 | Offline operator tool: produce one versioned archive for manual backend upload."""
from pathlib import Path
import json
import sys
import uuid
import zipfile

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools/ota'))
from sim_backend.release_store import upload, archive

def package(source,output,target,source_version,version,kind):
    source=Path(source).resolve()
    with source.open('rb') as stream:data=stream.read(16*1024*1024+1)
    work=ROOT/'logs/local_packager_work'/uuid.uuid4().hex
    entry=upload(data,target,source_version,version,kind,work)
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    final=output/entry['filename']
    # Exclusive creation never replaces an existing user package. No network call.
    with final.open('xb') as out:
        with zipfile.ZipFile(archive(entry['id'],work)) as origin:
            with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_STORED) as dest:
                for name in origin.namelist():dest.writestr(name,origin.read(name))
                dest.writestr('release.json',json.dumps(entry,ensure_ascii=False,indent=2))
    with zipfile.ZipFile(final) as check:
        if check.testzip() is not None or check.read('payload.bin')!=data:
            raise ValueError('输出包读回失败，请勿上传')
    return dict(file=str(final),**entry)

# SAM | 2026-10-22 +08:00 | User requires both firmwares in one package; --- separates whole-product source and target versions.
def main():
    import tkinter as tk
    from tkinter import ttk,filedialog,messagebox
    from local_packager.bundle import bundle, validate_upgrade
    window=tk.Tk();window.title('YP001 双固件OTA打包工具');window.geometry('880x650')
    window.minsize(800,600)
    frame=ttk.Frame(window,padding=20);frame.pack(fill='both',expand=True)
    ttk.Label(frame,text='5526 + CAT1 → 一个版本包 → 手动上传后台',font=('Microsoft YaHei UI',15)).grid(row=0,column=0,columnspan=3,sticky='w',pady=(0,14))
    variables={k:tk.StringVar() for k in ['gr','cat','output','source','version','prefix','suffix']}
    variables['prefix'].set('YP001');variables['output'].set(str(ROOT/'OTA打包输出'))
    rows=[('gr','GR5526 固件'),('cat','CAT1 固件'),('source','整机源版本（例如1.0）'),('version','整机目标版本（例如1.3）'),('prefix','包名前缀（可改）'),('suffix','包名后缀（可改）'),('output','输出目录')]
    for row,(key,title) in enumerate(rows,start=1):
        ttk.Label(frame,text=title).grid(row=row,column=0,sticky='w',pady=7)
        ttk.Entry(frame,textvariable=variables[key]).grid(row=row,column=1,sticky='ew',padx=10)
        if key in ('gr','cat','output'):
            def choose(k=key):
                selected=filedialog.askdirectory(title='选择输出目录') if k=='output' else filedialog.askopenfilename(title='选择'+('GR5526' if k=='gr' else 'CAT1')+'固件')
                if selected:variables[k].set(selected)
            ttk.Button(frame,text='选择目录' if key=='output' else '选择固件',command=choose).grid(row=row,column=2)
    frame.columnconfigure(1,weight=1)
    preview=tk.StringVar()
    def update_preview(*_):
        source,target=variables['source'].get().strip(),variables['version'].get().strip()
        try:
            version=validate_upgrade(source,target)
            names=[variables['prefix'].get().strip(),version,variables['suffix'].get().strip()]
            preview.set('文件名：'+'_'.join(x for x in names if x)+'_<唯一编号>.ypota.zip')
        except ValueError as exc:preview.set(str(exc))
    for v in variables.values():v.trace_add('write',update_preview)
    update_preview()
    ttk.Label(frame,textvariable=preview,wraplength=790).grid(row=8,column=0,columnspan=3,sticky='w',pady=10)
    ttk.Label(frame,text='固定格式：源版本---目标版本，例如1.0---1.3。名称不参与版本比较。\n必须同时包含两份固件；后台拆分后顺序升级，不同时执行两端OTA。\n填写版本不会修改固件内版本；当前测试签名归档仍需原生包/端侧安装准入。',wraplength=790).grid(row=9,column=0,columnspan=3,sticky='w',pady=10)
    status=tk.StringVar(value='离线打包，不自动上传或烧录。')
    ttk.Label(frame,textvariable=status,wraplength=790).grid(row=11,column=0,columnspan=3,sticky='w',pady=12)
    def generate():
        button.config(state='disabled');window.update_idletasks()
        try:
            v={k:x.get().strip() for k,x in variables.items()}
            if not v['gr'] or not v['cat'] or not v['output']:raise ValueError('必须选择5526、CAT1两份固件和输出目录')
            result=bundle(v['gr'],v['cat'],v['output'],v['source'],v['version'],v['prefix'],v['suffix'])
            status.set('生成完成：'+result['file'])
            messagebox.showinfo('双固件打包完成',result['file']+'\n\n整机升级版本：'+result['upgrade']+'\n包含GR5526和CAT1；请手动上传后台。\n当前未批准直接设备安装。')
        except Exception as exc:
            status.set('打包失败：'+str(exc));messagebox.showerror('打包失败',str(exc))
        finally:button.config(state='normal')
    button=ttk.Button(frame,text='生成双固件版本包',command=generate)
    button.grid(row=10,column=0,columnspan=3,sticky='ew')
    window.mainloop()

if __name__=='__main__':main()
