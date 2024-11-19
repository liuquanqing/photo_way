import os
import sys
import json
import PyInstaller.__main__

def get_version_from_config():
    """从 config.json 读取版本号"""
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
            return config.get('version', '1.0.0')
    except:
        return '1.0.2'

def build():
    version = get_version_from_config()
    
    opts = [
        'photo_way.py',
        '--onefile',         # 单文件
        '--windowed',        # 无控制台
        f'--name=PhotoOrganizer_v{version}',
        '--clean',           # 清理缓存
        '--noconfirm',       # 不询问确认
        
        # 添加配置文件
        '--add-data=config.json;.',  
        
        # 性能优化
        '--disable-windowed-traceback'
    ]
    
    if os.path.exists('icon.ico'):
        opts.append('--icon=icon.ico')
    
    PyInstaller.__main__.run(opts)

if __name__ == "__main__":
    build()