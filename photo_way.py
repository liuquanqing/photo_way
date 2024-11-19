# -*- coding: utf-8 -*-
import os
import shutil
from datetime import datetime
import re
from PIL import Image
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from threading import Thread
import queue
import warnings
import json
import os.path
import logging
from logging.handlers import RotatingFileHandler
from concurrent.futures import ThreadPoolExecutor, as_completed
import multiprocessing
import fnmatch
import sys
import subprocess
import tkinter.font as tkfont
import time
import psutil

warnings.filterwarnings("ignore", category=Image.DecompressionBombWarning)

class ModernButton(ttk.Button):
    """Custom modern style button"""
    def __init__(self, master=None, **kwargs):
        style_name = kwargs.pop('style', 'Modern.TButton')
        super().__init__(master, style=style_name, **kwargs)

class PhotoOrganizerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("照片整理助手")
        
        # 添加进度条变量初始化
        self.progress_var = tk.DoubleVar(value=0)  # 添加这一行
        
        # 设置窗口最小尺寸 - 使用黄金比例
        min_width = 800  # 基础度
        min_height = int(min_width * 1.618)  # 黄金比例
        root.minsize(min_width, min_height)  # 约为 800 x 1294
        
        # 设置日志
        self.setup_logging()
        self.logger.info("程序启动")
        
        # 设置配置文件路径 - 修复括号闭合问题
        try:
            # 获取用户主目录下的配置目录
            config_dir = os.path.join(os.path.expanduser("~"), ".photo_organizer", "config")
            os.makedirs(config_dir, exist_ok=True)
            
            # 设置配置文件完整路径
            self.config_file = os.path.join(config_dir, "config.json")
            
            # 记录配置信息
            self.logger.info(f"配置目录: {config_dir}")
            self.logger.info(f"配置文件: {self.config_file}")
            
        except Exception as e:
            # 如果出错,使用当前目录作为备选
            fallback_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
            self.logger.error(f"设置配置路径出错: {str(e)}, 使用备选路径: {fallback_path}")
            self.config_file = fallback_path
        
        # 记录配置文件路径
        self.logger.info(f"配置文件路径: {self.config_file}")
        
        # 初始化队列
        self.progress_queue = queue.Queue()
        self.running = False
        
        # 先加载设置
        self.settings = self.load_settings()
        
        # 初始化所有变量 - 使用加载的配置
        self.organize_by_month_var = tk.StringVar(value=self.settings.get('organize_by_month', 'month'))
        self.move_files_var = tk.BooleanVar(value=self.settings.get('move_files', False))
        self.include_subfolders_var = tk.BooleanVar(value=self.settings.get('include_subfolders', True))
        self.cleanup_enabled = tk.BooleanVar(value=self.settings.get('cleanup_enabled', True))
        self.check_duplicates_var = tk.BooleanVar(value=self.settings.get('check_duplicates', True))
        self.time_method_vars = [tk.BooleanVar(value=val) for val in self.settings.get('time_methods', [True, True, True])]
        
        # 计缩放子
        self.scale_factor = self.calculate_scale_factor()
        
        # 初始化颜色方案
        self.colors = {
            'primary': '#4F46E5',       # 靛蓝色
            'primary_dark': '#4338CA',  # 深靛蓝色
            'accent': '#818CF8',        # 浅靛蓝色
            'bg': '#F9FAFB',           # 浅灰背景
            'card': '#FFFFFF',         # 纯白卡片
            'text': '#111827',         # 深色文字
            'text_secondary': '#6B7280', # 次要文字
            'text_light': '#9CA3AF',    # 浅色文字
            'text_disabled': '#D1D5DB', # 添加禁用状态的文字颜色
            'border': '#E5E7EB',       # 边框色
            'success': '#059669',      # 深绿色
            'warning': '#D97706',      # 琥珀色
            'error': '#DC2626',        # 红色
            'progress_bg': '#EEF2FF',   # 进度条背景
            'progress_fill': '#4F46E5'  # 进度条填充色
        }
        
        # 初始化字体
        system_font = self.get_system_font()
        self.fonts = {
            'title': (system_font, self.scaled(20), 'bold'),
            'subtitle': (system_font, self.scaled(14)),
            'heading': (system_font, self.scaled(12)),
            'body': (system_font, self.scaled(10)),
            'button': (system_font, self.scaled(10)),
            'small': (system_font, self.scaled(8))
        }
        
        # 置式
        self.setup_styles()
        
        # 创建框架
        self.main_frame = ttk.Frame(root, style='Main.TFrame')
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=self.scaled(20), pady=self.scaled(30))
        
        # 创建UI
        self.create_widgets()
        
        # 用保存的路径
        if 'source_dir' in self.settings:
            self.source_entry.insert(0, self.settings['source_dir'])
        if 'target_dir' in self.settings:
            self.target_entry.insert(0, self.settings['target_dir'])
        
        # 检查进度队列
        self.check_progress_queue()
        
        # 在初始化时获取系统配置
        self.max_workers, self.batch_size = self.get_optimal_config()
        
        # 创建线程池时使用优化后的配置
        self.executor = ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix='PhotoWorker'
        )
        
        # 添加性能监控
        self.monitor_system_resources()
        
        # 在窗口关闭时保存设置
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        self.total_files = 0
        self.processed_files = 0
        self.processed_files_by_type = []  # 添加这一行来记录处理过的文件
        
        # 检查是否首次运行，只在首次运行时自动显示欢迎弹窗
        if self.settings.get('first_run', True):
            self.root.after(500, lambda: self.show_welcome(auto_show=True))
            # 更新配置，标记已非首次运行
            self.settings['first_run'] = False
            self.save_settings()

    def setup_logging(self):
        """设置日志记录"""
        # 在用户目录下创建日志文件夹
        log_dir = os.path.join(os.path.expanduser("~"), ".photo_organizer", "logs")
        os.makedirs(log_dir, exist_ok=True)
        
        # 设置日志文件名（包含日期）
        log_file = os.path.join(log_dir, f"photo_organizer_{datetime.now().strftime('%Y%m%d')}.log")
        
        # 配置日志器
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                RotatingFileHandler(
                    log_file, 
                    maxBytes=10*1024*1024,  # 10MB
                    backupCount=5,
                    encoding='utf-8'
                ),
                logging.StreamHandler()  # 同时输出到控制台
            ]
        )
        
        self.logger = logging.getLogger('PhotoOrganizer')
        self.logger.info("程序启动")
        self.logger.info(f"日志文件路径: {log_file}")  # 添加日志文件路径的记录

    def log_message(self, message, level='info'):
        """优化的日志显示"""
        try:
            # 获取当前时间
            current_time = datetime.now().strftime("%H:%M:%S")
            
            # 根据不同类型的消���示格式
            if "已移动:" in message or "已复制:" in message:
                # 简化文件操作的显示
                filename = os.path.basename(message.split("->")[1].strip())
                formatted_message = f"{current_time} ➜ {filename}"
            elif "跳过" in message:
                # 简化跳过文件的显示
                filename = os.path.basename(message.split(":")[1].strip())
                formatted_message = f"{current_time} • 跳过: {filename}"
            elif "错误" in message:
                # 错误信息保持完整
                formatted_message = f"{current_time} ✕ {message}"
            elif "共找到" in message:
                # 文件统计信息
                formatted_message = f"{current_time} → {message}"
            else:
                # 其他信息简化显示
                formatted_message = f"{current_time} • {message}"
                
            # 在文本框开始处插入消息并换行
            self.log_text.insert('1.0', formatted_message + '\n')
            
            # 应用相应的标签样式
            line_start = "1.0"
            line_end = "2.0"
            
            # 根据消息类型设置颜色
            if level == 'error' or "错误" in message:
                self.log_text.tag_add('error', line_start, line_end)
            elif level == 'warning' or "警告" in message:
                self.log_text.tag_add('warning', line_start, line_end)
            elif "跳过" in message:
                self.log_text.tag_add('skip', line_start, line_end)
            else:
                self.log_text.tag_add('info', line_start, line_end)
                
            # 限制日志显示行数
            if int(self.log_text.index('end-1c').split('.')[0]) > 100:
                self.log_text.delete('end-50c', 'end')
                
        except Exception as e:
            print(f"记录日志失败: {str(e)}")

    def browse_source(self):
        """选择源文件夹"""
        folder = filedialog.askdirectory(title="选择源文件夹")
        if folder:
            self.source_entry.delete(0, tk.END)
            self.source_entry.insert(0, folder)
            self.save_settings()  # 保存设置
            self.log_message(f"已选择源文件夹: {folder}")

    def browse_target(self):
        """选择目标文件夹"""
        folder = filedialog.askdirectory(title="选择目标文件夹")
        if folder:
            self.target_entry.delete(0, tk.END)
            self.target_entry.insert(0, folder)
            self.save_settings()  # 存设置
            self.log_message(f"已选择目标文件夹: {folder}")

    def stop_organize(self):
        """停止整理"""
        try:
            if messagebox.askyesno("确认", "确定要停止处理吗？"):
                self.running = False
                self.logger.info("用户手动停止处理")
                
                # 确保在主线程中更新UI
                self.root.after(0, lambda: self.status_label.configure(text="已停止"))
                
                # 记录日志
                self.log_message("处理已停止", level='warning')
                
        except Exception as e:
            self.logger.error(f"停止处理时出错: {str(e)}")
            self.log_message(f"停止处理时出错: {str(e)}", level='error')

    def process_files(self, source_dir, target_dir):
        """处理文件的主函数"""
        try:
            start_time = time.time()
            # 获取所有文件
            all_files = self.get_all_files(source_dir)
            if not all_files:
                self.progress_queue.put(("message", "未找到需要处理的文件"))
                self.root.after(0, lambda: self.start_button.configure(state=tk.NORMAL))
                self.root.after(0, lambda: self.stop_button.configure(state=tk.DISABLED))
                return
                
            # 保存总文件数和已处理数量 - 修改为整数计数
            self.total_files = len(all_files)
            self.processed_files = 0
            self.skipped_files = 0
            self.duplicate_files = 0
            self.cleaned_dirs = 0
            self.error_files = []
            
            self.progress_queue.put(("message", f"共找到 {self.total_files} 个文件需要处理"))
            
            # 初始化进度显示
            self.progress_queue.put(("status", f"已处理: 0/{self.total_files}"))
            
            # 处理每个文件
            for file_path in all_files:
                if not self.running:
                    self.logger.info("检测到停止信号")
                    break
                    
                try:
                    result = self.process_single_file(file_path, target_dir)
                    if result:  # 只有处理成功才计数
                        self.processed_files += 1  # 使用加法而不是add方法
                    else:
                        self.skipped_files += 1
                    
                    # 更新进度和状态
                    progress = (self.processed_files / self.total_files) * 100
                    self.progress_queue.put(("progress", progress))
                    self.progress_queue.put(("status", f"已处理: {self.processed_files}/{self.total_files}"))
                    
                    # 更新进度标签
                    self.root.after(0, lambda: self.progress_status.configure(
                        text=f"已处理: {self.processed_files}/{self.total_files}"
                    ))
                    self.root.after(0, lambda: self.progress_percent.configure(
                        text=f"{progress:.1f}%"
                    ))
                    
                except Exception as e:
                    self.logger.error(f"处理文件失败 {file_path}: {str(e)}")
                    self.error_files.append((file_path, str(e)))
                    continue
            
            # 理完成后发送完成消息
            end_time = time.time()
            duration = round(end_time - start_time, 1)
            
            # 构建详细的结果日志
            result_log = [
                f"处理完成! 耗时: {duration}秒",
                f"源目录: {source_dir}",
                f"目标目录: {target_dir}",
                f"处理文件总数: {self.total_files}个",
                f"成功处理: {self.processed_files}个",
                f"跳过文件: {self.skipped_files}个"
            ]
            
            # 如果启用了重复检查，添加重复文件信息
            if self.check_duplicates_var.get():
                result_log.append(f"发现重复文件: {self.duplicate_files}个")
                
            # 如果有错误文件，添加错误信息
            if self.error_files:
                result_log.append(f"处理失败: {len(self.error_files)}个")
                
            # 如果启用了清理空目录，添加清理信息
            if self.cleanup_enabled.get():
                result_log.append(f"清理空目录: {self.cleaned_dirs}个")
                
            # 添加移动/复制模式信息
            mode = "移动" if self.move_files_var.get() else "复制"
            result_log.append(f"操作模式: {mode}")
            
            # 添加时间获取方式信息
            time_methods = []
            if self.time_method_vars[0].get(): time_methods.append("EXIF")
            if self.time_method_vars[1].get(): time_methods.append("文件名")
            if self.time_method_vars[2].get(): time_methods.append("修改时间")
            result_log.append(f"时间获取方式: {', '.join(time_methods)}")
            
            # 加组织式息
            organize_by = "���/月" if self.get_organize_by_month() == "month" else "年"
            result_log.append(f"文件组织方式: {organize_by}")
            
            # 如果有处理失败的文件，添加详细信息
            if self.error_files:
                result_log.append("\n处理失败的文件:")
                for file, error in self.error_files[:5]:  # 只显示前5个错误
                    result_log.append(f"- {os.path.basename(file)}: {error}")
                if len(self.error_files) > 5:
                    result_log.append(f"... 等共{len(self.error_files)}个文件处理失败")
            
            # 在日志区域显示结果
            self.log_text.configure(state='normal')
            self.log_text.delete(1.0, tk.END)
            self.log_text.insert(tk.END, "\n".join(result_log))
            self.log_text.configure(state='disabled')
            
            # 自动滚动到顶部
            self.log_text.see("1.0")
            
            # 如果有错误，弹出提示
            if self.error_files:
                messagebox.showwarning("处理完成", 
                    f"处理完成，但有{len(self.error_files)}个文件处理失败，详细信息请查看日志。")
            else:
                messagebox.showinfo("处理完成", 
                    f"所有文件处理完成！\n共处理: {self.processed_files}个文件\n耗时: {duration}秒")
            
            # 显示最终结果
            self._show_final_results(
                self.total_files, 
                self.processed_files, 
                len(self.error_files), 
                self.skipped_files, 
                duration
            )
            
        except Exception as e:
            self.logger.error(f"处理错误: {str(e)}", exc_info=True)
            self.progress_queue.put(("message", f"处理出错: {str(e)}"))
        finally:
            # 确保在任何情况下都重置按钮状态
            self.root.after(0, lambda: self.start_button.configure(state=tk.NORMAL))
            self.root.after(0, lambda: self.stop_button.configure(state=tk.DISABLED))

    def _adjust_batch_size(self):
        """动态调整批次大"""
        try:
            # 获取当前统状态
            cpu_percent = psutil.cpu_percent()
            memory = psutil.virtual_memory()
            
            # 据CPU和内存动态调整
            if cpu_percent > 80 or memory.percent > 85:
                self.batch_size = max(20, self.batch_size // 2)
                self.logger.warning(f"系统资源紧张，调整批处理大小: {self.batch_size}")
                
            # 检查磁盘空间
            disk = psutil.disk_usage(self.target_entry.get())
            if disk.percent > 90:
                self.logger.warning("目标磁盘空间不足")
                
        except Exception as e:
            self.logger.error(f"监控资源失败: {str(e)}")

    def _show_initial_info(self, source_dir, target_dir):
        """显示初始处理信息"""
        self.log_message("📷 开始处理照片...")
        self.log_message(f"📁 源目录: {source_dir}")
        self.log_message(f"📁 目标目录: {target_dir}")
        
        # 显示当前设置
        self.log_message("\n⚙️ 当前设置:")
        self.log_message(f"├─ 整理方式: {'按年月' if self.organize_by_month_var.get() == 'month' else '仅按年'}")
        self.log_message(f"├ {'移动' if self.move_files_var.get() else '复制'}文件")
        self.log_message(f"├─ {'包含' if self.include_subfolders_var.get() else '不包含'}子目录")
        self.log_message(f"├─ {'启用' if self.cleanup_enabled.get() else '禁用'}清理空目录")
        self.log_message(f"└─ {'检查' if self.check_duplicates_var.get() else '不检'}重复文件")

    def _update_progress_status(self, total, success, errors, skipped, start_time):
        """进度状态"""
        try:
            # 计算进度百分比
            progress = min((success + skipped) / max(total, 1) * 100, 100)
            
            # 更新进度条
            self.progress_queue.put(("progress", progress))
            
            # 计算速度和时间
            elapsed_time = time.time() - start_time
            speed = total / elapsed_time if elapsed_time > 0 else 0
            
            # 状态显示（包含进度百分比
            status = f"处理: {success}/{total} ({progress:.1f}%) | 错误: {errors} | {speed:.1f}个/秒"
            self.logger.debug(f"更态: {status}")
            self.progress_queue.put(("status", status))
            
        except Exception as e:
            self.logger.error(f"更新进度状态出错: {str(e)}")

    def _show_final_results(self, total, success, errors, skipped, total_time):
        """显示最终处理结果"""
        try:
            # 确保进度条显示100%
            self.progress_queue.put(("progress", 100))
            
            # 获取不同类型文件的统计
            photos_count = sum(1 for f in self.processed_files_by_type if f.endswith(('.jpg', '.jpeg', '.png', '.heic')))
            videos_count = sum(1 for f in self.processed_files_by_type if f.endswith(('.mp4', '.mov', '.avi')))
            gif_count = sum(1 for f in self.processed_files_by_type if f.endswith('.gif'))
            raw_count = sum(1 for f in self.processed_files_by_type if f.endswith(('.raw', '.cr2', '.nef', '.arw')))
            
            # 构建摘要信息并显示在日志中
            summary = (
                "\n" + "="*70 + "\n"
                "                         处理完成统计报告\n" 
                "="*70 + "\n\n"
                f"[整体情况]\n"
                f"    总计处理: {total} 个文件  |  耗时: {self._format_time(total_time)}\n"
                f"    处理速度: {total/total_time:.1f} 个/秒  |  成率: {(success/total*100):.1f}%\n\n"
                f"[处理结果]\n"
                f"    成功处理: {success} 个文件\n"
                f"    处理失败: {errors} 个文件\n"
                f"    已跳过:   {skipped} 个文件\n\n"
                f"[文件类型统计]\n"
                f"    照片文件: {photos_count} 个  (.jpg/.jpeg/.png/.heic)\n"
                f"    视频文件: {videos_count} 个  (.mp4/.mov/.avi)\n"
                f"    GIF动图:  {gif_count} 个   (.gif)\n"
                f"    RAW文件:  {raw_count} 个   (.raw/.cr2/.nef/.arw)\n\n"
                f"[处理路径]\n"
                f"    源目录:   {self.source_entry.get()}\n"
                f"    目标目录: {self.target_entry.get()}\n\n"
                f"[处理配置]\n"
                f"    文件操作: {'移动' if self.move_files_var.get() else '复制'}文件\n"
                f"    子目录:   {'包含' if self.include_subfolders_var.get() else '不包含'}子目录\n"
                f"    重复文件: {'检查' if self.check_duplicates_var.get() else '不检查'}重复\n"
                f"    整理方式: {self.organize_by_month_var.get() == 'month' and '按年月' or '仅按年'}\n\n"
                "="*70 + "\n"
            )
            
            # 在日志开头插入摘要
            self.log_text.insert('1.0', summary)
            
            # 更新状态标签
            if errors == 0:
                self.status_label.configure(text=f"整理成功！")
            else:
                self.status_label.configure(text=f"整理完成: {success}/{total} ({(success/total*100):.1f}%)")
            
            # 如果有成功处理的文件，打开目标目录
            target_dir = self.target_entry.get().strip()
            if target_dir and os.path.exists(target_dir) and success > 0:
                self.open_directory(target_dir)
                
        except Exception as e:
            self.logger.error(f"显示最终结果时出错: {str(e)}")

    def _format_time(self, seconds):
        """格式化时间显示"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        seconds = int(seconds % 60)
        
        if hours > 0:
            return f"{hours}小时{minutes}分{seconds}秒"
        elif minutes > 0:
            return f"{minutes}分{seconds}秒"
        else:
            return "1分钟"  # 不到1分钟也显示1分钟

    def _file_scanner(self, file_iterator, file_queue):
        """文件扫描线程"""
        try:
            for file_path in file_iterator:
                if not self.running:
                    break
                file_queue.put(file_path)
                
            # 放入结束标记
            file_queue.put(None)
        except Exception as e:
            self.logger.error(f"文件扫描线程出错: {str(e)}")

    def iter_valid_files(self, source_dir):
        """生成有效文件的迭代器"""
        try:
            for root, _, files in os.walk(source_dir):
                # 如果不包含子目录且不是源目录，则跳过
                if not self.include_subfolders_var.get() and root != source_dir:
                    continue
                    
                for file in files:
                    if not self.running:
                        return
                        
                    file_path = os.path.join(root, file)
                    if self.is_valid_file(file_path):
                        yield file_path
                        
        except Exception as e:
            self.logger.error(f"遍历文时出错: {str(e)}")

    def _collect_batch(self, file_queue, scanner_thread):
        """收集一批文件进行处理"""
        try:
            batch = []
            for _ in range(self.batch_size):
                try:
                    # 等待0.1秒，如果有新文件且扫描线程已结束，则退出
                    file_path = file_queue.get(timeout=0.1)
                    if file_path is None:  # 扫描结束标记
                        break
                    batch.append(file_path)
                except queue.Empty:
                    if not scanner_thread.is_alive():
                        break
                    continue
            
            return batch
            
        except Exception as e:
            self.logger.error(f"集批次失败: {str(e)}")
            return []

    def start_organize(self):
        """开始整理照片"""
        try:
            source_dir = self.source_entry.get().strip()
            target_dir = self.target_entry.get().strip()
            
            if not source_dir or not target_dir:
                self.logger.warning("源目录或目标目录为空")
                messagebox.showerror("错误", "请选择源文件夹和目标文件夹")
                return
            
            # 更新UI状态 - 保在主线程中更新
            self.root.after(0, lambda: self.start_button.configure(state=tk.DISABLED))
            self.root.after(0, lambda: self.stop_button.configure(state=tk.NORMAL))
            self.running = True
            
            # 添加这一行，更新状态为"整理中"
            self.status_label.configure(text="整理中")
            
            # 重置进度
            self.progress_var.set(0)
            
            # 启动进度检查
            self.check_progress_queue()
            
            # 启动处理线程
            Thread(target=self.process_files, args=(source_dir, target_dir), daemon=True).start()
            
        except Exception as e:
            self.logger.error(f"启动失败: {str(e)}", exc_info=True)
            messagebox.showerror("错误", f"启动失败: {str(e)}")

    def setup_styles(self):
        """设置样式"""
        style = ttk.Style()
        
        # 进度条式
        style.configure(
            'Custom.Horizontal.TProgressbar',
            troughcolor=self.colors['progress_bg'],
            background=self.colors['progress_fill'],
            thickness=self.scaled(12),  # 调整进度条高度
            borderwidth=0  # 移除边框
        )
        
        # 确保进度条能显示文本
        style.layout('Custom.Horizontal.TProgressbar', 
                    [('Horizontal.Progressbar.trough',
                      {'children': [('Horizontal.Progressbar.pbar',
                                   {'side': 'left', 'sticky': 'ns'})],
                       'sticky': 'nswe'})])
        
        # 进度状态标签样式
        style.configure(
            'Status.TLabel',
            padding=(self.scaled(5), self.scaled(2)),
            font=self.fonts['body'],
            background=self.colors['bg'],
            foreground=self.colors['text']
        )
        
        # 使用系统默认字体
        system_font = self.get_system_font()
        
        # 调整字体大小和字重
        self.fonts = {
            'title': (system_font, self.scaled(20), 'bold'),     # 添加 bold 使标题更重
            'subtitle': (system_font, self.scaled(14)),
            'heading': (system_font, self.scaled(12)),
            'body': (system_font, self.scaled(10)),
            'button': (system_font, self.scaled(10)),
            'small': (system_font, self.scaled(8))
        }
        
        # 置框架样式
        style.configure('Main.TFrame',
                       background=self.colors['bg'])
        
        # 配置片样式
        style.configure('Card.TFrame',
                       background=self.colors['card'],
                       relief='flat')
        
        # 配标签样式
        style.configure('Title.TLabel',
                       font=self.fonts['title'],
                       background=self.colors['bg'],
                       foreground=self.colors['text'])
                       
        style.configure('Subtitle.TLabel',
                       font=self.fonts['subtitle'],
                       background=self.colors['bg'],
                       foreground=self.colors['text_secondary'])
                       
        # 配置按样
        button_padding = (self.scaled(10), self.scaled(4))   # 从(20,8)为(15,6)
        style.configure('Primary.TButton',
                       font=self.fonts['button'],
                       padding=button_padding)
                       
        style.configure('Secondary.TButton',
                       font=self.fonts['button'],
                       padding=button_padding)
                       
        # 配置输入框样式
        entry_padding = (self.scaled(4), self.scaled(2))     # 从(8,6)改为(6,4)
        style.configure('Custom.TEntry',
                       font=self.fonts['body'],
                       padding=entry_padding)
                       
        # 配置度条样式 - 高度和圆角
        style.configure('Custom.Horizontal.TProgressbar',
                       background=self.colors['progress_fill'],    # 进度填色
                       troughcolor=self.colors['progress_bg'],     # 进度条背景色
                       bordercolor=self.colors['border'],          # 边框色
                       lightcolor=self.colors['progress_fill'],    # 高亮
                       darkcolor=self.colors['progress_fill'],     # 暗部色
                       thickness=self.scaled(12))                  # 增加高度到16
        
        # 添加缺失的自定义样式配置
        style.configure('Custom.TCheckbutton',
                       font=self.fonts['body'],
                       background=self.colors['card'])
                       
        style.configure('Custom.TRadiobutton',
                       font=self.fonts['body'],
                       background=self.colors['card'])
        
        # 强制更新样式
        style.configure('TLabel', font=self.fonts['body'])
        style.configure('TButton', font=self.fonts['button'])
        
        # 刷新所有widget的样式
        def update_widget_styles(widget):
            widget.update()
            for child in widget.winfo_children():
                update_widget_styles(child)
        
        # 在创建完有件调用
        self.root.after(100, lambda: update_widget_styles(self.root))
        
        # 添小字样式
        style.configure('Small.TLabel',
                       font=('Microsoft YaHei UI', self.scaled(10)),  # 使用更小的字号
                       background=self.colors['bg'],
                       foreground=self.colors['text_secondary'])

        # 添加签框架样式
        style.configure('Card.TLabelframe', 
                       background=self.colors['card'],
                       relief='flat')
        style.configure('Card.TLabelframe.Label',
                       background=self.colors['card'],
                       foreground=self.colors['text'],
                       font=self.fonts['heading'])

        # 添小型次要按钮样式
        style.configure('Small.TButton',
                       font=self.fonts['small'],
                       padding=(self.scaled(8), self.scaled(2)),
                       background=self.colors['bg'],
                       foreground=self.colors['text_secondary'])
        
        # 更新颜色方案，添加浅色背景
        self.colors.update({
            'text_light': '#757575',      # 的文字颜色
            'bg_light': '#F5F5F5',        # 浅色背景
            'scrollbar': '#E0E0E0'        # 滚动条颜色
        })

        # 在 setup_styles 方法中添加以下样式配置
        
        # 配置单选按钮样 - 使用统一的灰色主题
        style.configure('Custom.TRadiobutton',
                       font=self.fonts['body'],
                       background=self.colors['card'],
                       foreground=self.colors['text'])
        
        # 设置单选按钮中时的颜色状态 - 使用统一的灰色
        style.map('Custom.TRadiobutton',
                  background=[('active', self.colors['bg_light']),
                             ('selected', self.colors['card'])],
                  foreground=[('active', self.colors['text']),
                             ('selected', self.colors['text'])],
                  indicatorcolor=[('selected', self.colors['text']),        # 从 primary 改为 text
                                ('!selected', self.colors['text_light'])])  # 选中时为浅灰色
        
        # 配置复选框样式 - 保持一致的灰色主题
        style.configure('Custom.TCheckbutton',
                       font=self.fonts['body'],
                       background=self.colors['card'],
                       foreground=self.colors['text'])
        
        # 设置复选框选中时的颜色
        style.map('Custom.TCheckbutton',
                  background=[('active', self.colors['bg_light'])],
                  indicatorcolor=[('selected', self.colors['text']),        # 从 primary 改为 text
                                ('!selected', self.colors['text_light'])])  # 未选中为浅灰色

        # 添加链接样式按钮
        style.configure('Link.TButton',
                       font=('Microsoft YaHei UI', self.scaled(10)),
                       background=self.colors['bg'],
                       foreground=self.colors['text_secondary'],
                       borderwidth=0,
                       padding=0)
        style.map('Link.TButton',
                  foreground=[('active', self.colors['text'])])  # 悬停时变深

    def create_widgets(self):
        """创建现代化界面元素"""
        # 标题域
        title_frame = ttk.Frame(self.main_frame, style='Main.TFrame')
        title_frame.pack(fill=tk.X, pady=(0, self.scaled(10)))  # 从20改为10
        
        # 标题和副标题容器
        left_padding = self.scaled(20)
        title_inner = ttk.Frame(title_frame, style='Main.TFrame')
        title_inner.pack(fill=tk.X, padx=left_padding)
        
        # 创建标题行架，用于放置标题和作者信息
        title_line = ttk.Frame(title_inner, style='Main.TFrame')
        title_line.pack(fill=tk.X)
        
        # 标（左对齐）
        ttk.Label(title_line,
                 text="照片整理助手",
                 style='Title.TLabel').pack(side=tk.LEFT)
                 
        # 版本号、更新日志作者右对齐，最小与标题距离
        version_author = ttk.Frame(title_line, style='Main.TFrame')
        version_author.pack(side=tk.RIGHT, pady=self.scaled(12))
        
        # 只保留版本说明按钮，移除使用说明按钮
        ttk.Button(version_author,
                  text="v1.0.2 说明",  # 更新版本号
                  command=self.show_changelog,
                  style='Link.TButton').pack(side=tk.LEFT, padx=(0, self.scaled(10)))
                 
        ttk.Label(version_author,
                 text="作者：lqq",
                 style='Small.TLabel',
                 foreground=self.colors['text_secondary']).pack(side=tk.LEFT)
        
        # 副标题（单独一行）
        ttk.Label(title_inner,
                 text="简单高效地整理您的照片库",
                 style='Subtitle.TLabel').pack(anchor='w', pady=(self.scaled(5), 0))

        # 文件选择区域 - 使用卡片式设计
        file_card = ttk.Frame(self.main_frame, style='Card.TFrame')
        file_card.pack(fill=tk.X, pady=self.scaled(5))  # 从10改为5
        
        # 添加内间距
        file_inner_frame = ttk.Frame(file_card, style='Card.TFrame')
        file_inner_frame.pack(fill=tk.X, padx=self.scaled(15), pady=self.scaled(15))  # 从20改为15
        
        # 源文件夹选择
        source_frame = ttk.Frame(file_inner_frame, style='Card.TFrame')
        source_frame.pack(fill=tk.X, pady=(0, self.scaled(15)))
        
        ttk.Label(source_frame,
                 text="源文件夹",
                 width=10,  # 固定标签宽度
                 font=self.fonts['body']).pack(side=tk.LEFT, padx=(0, self.scaled(15)))
                 
        self.source_entry = ttk.Entry(source_frame,
                                    font=self.fonts['body'],
                                    style='Custom.TEntry')
        self.source_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, self.scaled(15)))
        
        ttk.Button(source_frame,
                  text="选择",
                  width=6,  # 固定按钮宽度
                  command=self.browse_source,
                  style='Primary.TButton').pack(side=tk.LEFT)
        
        # 标文件夹择
        target_frame = ttk.Frame(file_inner_frame, style='Card.TFrame')
        target_frame.pack(fill=tk.X)
        
        ttk.Label(target_frame,
                 text="目标文件夹",
                 width=10,  # 固定标签宽度
                 font=self.fonts['body']).pack(side=tk.LEFT, padx=(0, self.scaled(15)))
                 
        self.target_entry = ttk.Entry(target_frame,
                                    font=self.fonts['body'],
                                    style='Custom.TEntry')
        self.target_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, self.scaled(15)))
        
        ttk.Button(target_frame,
                  text="选择",
                  width=6,  # 固定按钮宽度
                  command=self.browse_target,
                  style='Primary.TButton').pack(side=tk.LEFT)

        # 项区域
        options_card = ttk.Frame(self.main_frame, style='Card.TFrame')
        options_card.pack(fill=tk.X, pady=self.scaled(10))  # 从15改为10
        
        options_inner = ttk.Frame(options_card, style='Card.TFrame')
        options_inner.pack(fill=tk.X, padx=self.scaled(10), pady=self.scaled(10))  # 从15改为10
        
        # 1. 整理方式
        organize_frame = ttk.LabelFrame(options_inner, text="整理方式", style='Card.TLabelframe')
        organize_frame.pack(fill=tk.X, pady=(0, self.scaled(5)))  # 从8改为5
        
        organize_inner = ttk.Frame(organize_frame, style='Card.TFrame')
        organize_inner.pack(fill=tk.X, padx=self.scaled(15), pady=self.scaled(8))
        
        # 创建单选按钮
        ttk.Radiobutton(
            organize_inner, 
            text="按年月", 
            variable=self.organize_by_month_var,
            value="month",
            style='Custom.TRadiobutton'
        ).pack(side=tk.LEFT, padx=(0, self.scaled(20)))
        
        ttk.Radiobutton(
            organize_inner, 
            text="仅按年", 
            variable=self.organize_by_month_var,
            value="year",
            style='Custom.TRadiobutton'
        ).pack(side=tk.LEFT)
        
        # 2. 处理选项
        process_frame = ttk.LabelFrame(options_inner, text="处理选项", style='Card.TLabelframe')
        process_frame.pack(fill=tk.X, pady=(0, self.scaled(5)))  # 从8改为5
        
        process_inner = ttk.Frame(process_frame, style='Card.TFrame')
        process_inner.pack(fill=tk.X, padx=self.scaled(15), pady=self.scaled(8))
        
        self.move_files_var = tk.BooleanVar(value=self.settings.get('move_files', False))
        self.include_subfolders_var = tk.BooleanVar(value=self.settings.get('include_subfolders', True))
        self.cleanup_enabled = tk.BooleanVar(value=True)
        self.check_duplicates_var = tk.BooleanVar(value=True)
        
        ttk.Checkbutton(process_inner, text="移动文件", 
                        variable=self.move_files_var,
                        style='Custom.TCheckbutton').pack(side=tk.LEFT, padx=(0, self.scaled(20)))
        ttk.Checkbutton(process_inner, text="子文件夹", 
                        variable=self.include_subfolders_var,
                        style='Custom.TCheckbutton').pack(side=tk.LEFT, padx=(0, self.scaled(20)))
        ttk.Checkbutton(process_inner, text="清理空目录", 
                        variable=self.cleanup_enabled,
                        style='Custom.TCheckbutton').pack(side=tk.LEFT, padx=(0, self.scaled(20)))
        ttk.Checkbutton(process_inner, text="检查重复", 
                        variable=self.check_duplicates_var,
                        style='Custom.TCheckbutton').pack(side=tk.LEFT)
        
        # 3. 时间取
        time_frame = ttk.LabelFrame(options_inner, text="时间获取", style='Card.TLabelframe')
        time_frame.pack(fill=tk.X)
        
        time_inner = ttk.Frame(time_frame, style='Card.TFrame')
        time_inner.pack(fill=tk.X, padx=self.scaled(15), pady=self.scaled(8))
        
        self.time_method_vars = []
        time_methods = ["EXIF", "文件名", "修改时间"]
        saved_methods = self.settings.get('time_methods', [True, True, True])
        
        for i, method in enumerate(time_methods):
            var = tk.BooleanVar(value=saved_methods[i])
            self.time_method_vars.append(var)
            ttk.Checkbutton(time_inner, text=method, 
                           variable=var,
                           style='Custom.TCheckbutton').pack(side=tk.LEFT, 
                                                           padx=(0 if i == 0 else self.scaled(20), 
                                                                0 if i == len(time_methods)-1 else 0))

        # 创建主操作区域
        action_frame = ttk.Frame(self.main_frame, style='Card.TFrame')
        action_frame.pack(fill=tk.X, pady=(self.scaled(10), self.scaled(5)))  # 调整上下间距

        action_inner = ttk.Frame(action_frame, style='Card.TFrame')
        action_inner.pack(fill=tk.X, padx=self.scaled(15))  # 保持与其他区域相同的左右边距

        # 状态和按钮行优化
        status_button_frame = ttk.Frame(action_inner, style='Card.TFrame')
        status_button_frame.pack(fill=tk.X, pady=(self.scaled(5), self.scaled(10)))  # 调整内部间距

        # 状态标签优化
        self.status_label = ttk.Label(
            status_button_frame,
            text="准备就绪",
            font=self.fonts['body'],
            foreground=self.colors['text'],
            padding=(self.scaled(5), self.scaled(2)))  # 添加适当的内边距
        
        self.status_label.pack(side=tk.LEFT)

        # 按钮组对齐优化
        buttons_right = ttk.Frame(status_button_frame, style='Card.TFrame')
        buttons_right.pack(side=tk.RIGHT)

        # 停止按钮
        self.stop_button = ttk.Button(
            buttons_right,
            text="停止",
            width=8,  # 固定按钮宽度
            command=self.stop_organize,
            style='Secondary.TButton',
            state=tk.DISABLED
        )
        self.stop_button.pack(side=tk.RIGHT, padx=(self.scaled(10), 0))

        # 开始整理按钮
        self.start_button = ttk.Button(
            buttons_right,
            text="开始整理",
            width=10,  # 固定按钮宽度
            command=self.start_organize,
            style='Primary.TButton'
        )
        self.start_button.pack(side=tk.RIGHT)

        # 进度条区域 - 移除额外的内边距,使用与上方区域一致的对齐方式
        progress_frame = ttk.Frame(self.main_frame, style='Card.TFrame')
        progress_frame.pack(fill=tk.X, pady=self.scaled(3))  # 从5改为3
        
        # 进度条内容区域 - 使用与上方区域一致的内边距
        progress_inner = ttk.Frame(progress_frame, style='Card.TFrame')
        progress_inner.pack(fill=tk.X, padx=self.scaled(15))  # 使用统一的水平内边距
        
        # 进度状态行
        progress_status_frame = ttk.Frame(progress_inner, style='Card.TFrame')
        progress_status_frame.pack(fill=tk.X, pady=(0, self.scaled(5)))

        # 进度文本
        self.progress_status = ttk.Label(
            progress_status_frame,
            text="已完成: 0/0",
            font=self.fonts['body'],
            foreground=self.colors['text_secondary']
        )
        self.progress_status.pack(side=tk.LEFT)

        # 百分比文本
        self.progress_percent = ttk.Label(
            progress_status_frame,
            text="0%",
            font=self.fonts['body'],
            foreground=self.colors['text_secondary']
        )
        self.progress_percent.pack(side=tk.RIGHT)

        # 进度条
        self.progress_bar = ttk.Progressbar(
            progress_inner,  # 注意这里改为 progress_inner
            variable=self.progress_var,
            mode='determinate',
            style='Custom.Horizontal.TProgressbar'
        )
        self.progress_bar.pack(fill=tk.X, pady=(0, self.scaled(5)))  # 只保留底部间距

        # 日志区域 - 调整对齐
        # 创建包含日志标题和按钮的顶部框架
        header_frame = ttk.Frame(self.main_frame, style='Card.TFrame')
        header_frame.pack(fill=tk.X, pady=(self.scaled(5), self.scaled(3)))  # 减小上下边距
        
        # 日志标题区域 - 使用与上方区域一致的内边距
        header_inner = ttk.Frame(header_frame, style='Card.TFrame')
        header_inner.pack(fill=tk.X, padx=self.scaled(15))  # 使用统一的水平内边距
        
        # 左侧日志标题
        ttk.Label(header_inner, 
                 text="日志", 
                 style='Subtitle.TLabel',
                 font=self.fonts['heading'],
                 foreground=self.colors['text_secondary']).pack(side=tk.LEFT)

        # 右侧按钮组
        button_frame = ttk.Frame(header_inner, style='Card.TFrame')
        button_frame.pack(side=tk.RIGHT)

        # 清理按钮
        ttk.Button(button_frame,
                  text="清理",
                  width=6,  # 固定按钮宽度
                  command=self.clear_log,
                  style='Small.TButton').pack(side=tk.RIGHT, padx=(self.scaled(5), 0))

        # 重置按钮
        ttk.Button(button_frame,
                  text="重置",
                  width=6,  # 固定按钮宽度
                  command=self.clear_config,
                  style='Small.TButton').pack(side=tk.RIGHT, padx=(self.scaled(5), 0))

        # 查看完整日志按钮
        ttk.Button(button_frame,
                  text="查看日志",
                  width=8,  # 固定按钮宽度
                  command=self.open_log_file,
                  style='Small.TButton').pack(side=tk.RIGHT)

        # 日志文本区域
        text_frame = ttk.Frame(self.main_frame, style='Card.TFrame')
        # 添加底部留白，增加 pady 的第二个值
        text_frame.pack(fill=tk.BOTH, expand=True, pady=(0, self.scaled(15)))  # 增加底部留白
        
        text_inner = ttk.Frame(text_frame, style='Card.TFrame')
        text_inner.pack(fill=tk.BOTH, expand=True, padx=self.scaled(15))
        
        # 日志文本框
        self.log_text = tk.Text(
            text_inner,
            font=self.fonts['small'],
            wrap=tk.NONE,
            relief='flat',
            bg=self.colors['bg_light'],
            height=3,  # 修改为3行高度
            padx=self.scaled(5),
            pady=self.scaled(3)
        )
        
        # 设置文本标签样式
        self.log_text.tag_configure('error', 
            foreground=self.colors['error'],
            spacing1=self.scaled(2))  # 减小行间距
        self.log_text.tag_configure('warning',
            foreground=self.colors['warning'],
            spacing1=self.scaled(2))  # 减小行间距
        self.log_text.tag_configure('info',
            foreground=self.colors['text'],
            spacing1=self.scaled(2))  # 减小行间距
        self.log_text.tag_configure('skip',
            foreground=self.colors['text_secondary'],
            spacing1=self.scaled(2))  # 减小行间距
        
        # 创建滚动
        self.v_scrollbar = ttk.Scrollbar(text_inner, orient="vertical", command=self.log_text.yview)
        self.h_scrollbar = ttk.Scrollbar(text_inner, orient="horizontal", command=self.log_text.xview)
        
        # 配置文本框的滚动
        self.log_text.configure(
            yscrollcommand=self.update_scrollbar_y,
            xscrollcommand=self.update_scrollbar_x
        )
        
        # 使用网格布局
        self.log_text.grid(row=0, column=0, sticky="nsew", padx=(0, self.scaled(2)))
        self.v_scrollbar.grid(row=0, column=1, sticky="ns")
        self.h_scrollbar.grid(row=1, column=0, sticky="ew")
        
        # 置网格权重
        text_inner.grid_rowconfigure(0, weight=1)
        text_inner.grid_columnconfigure(0, weight=1)
        
        # 初始化时隐藏滚动条
        self.v_scrollbar.grid_remove()
        self.h_scrollbar.grid_remove()

    def calculate_scale_factor(self):
        """算DPI放因子"""
        try:
            # 获取主显示器DPI
            dpi = self.root.winfo_fpixels('1i')
            # 打印当前DPI和缩放因子，用于调试
            print(f"Current DPI: {dpi}")
            scale_factor = dpi / 96.0
            print(f"Scale factor: {scale_factor}")
            return scale_factor
        except:
            return 1.0  # 默认返回1.0

    def scaled(self, value):
        """缩放数值"""
        return int(value * self.scale_factor)

    def check_progress_queue(self):
        """检查进度队列并更UI"""
        try:
            while True:
                try:
                    msg_type, msg = self.progress_queue.get_nowait()
                    
                    if msg_type == "progress":
                        progress = float(msg)
                        self.progress_var.set(progress)
                        
                    elif msg_type == "status":
                        # 更新进度状态文本
                        self.root.after(0, lambda m=msg: self.progress_status.configure(text=m))
                        
                    elif msg_type == "message":
                        self.log_message(msg)
                        
                    elif msg_type == "complete":
                        self.status_label.configure(text="已完成")
                        self.start_button.configure(state=tk.NORMAL)
                        self.stop_button.configure(state=tk.DISABLED)
                        break
                    
                except queue.Empty:
                    break
                
            if self.running:
                self.root.after(100, self.check_progress_queue)  # 增加检查间隔到100ms
                
        except Exception as e:
            self.logger.error(f"检查进度队列时出错: {str(e)}")

    def calculate_eta(self):
        """计算计剩余时间"""
        try:
            # ... existing calculation code ...
            
            if self.speed_history:
                avg_speed = sum(self.speed_history) / len(self.speed_history)
                remaining_files = self.total_files - self.processed_files
                
                if avg_speed > 0:
                    remaining_time = remaining_files / avg_speed
                    # 直接返回时间数值，不带"约"字
                    return self._format_time(remaining_time)

            return "计算中..."
            
        except Exception as e:
            self.logger.error(f"计算ETA时出错: {str(e)}")
            return "计算中..."

    def _format_time(self, seconds):
        """更简洁的时间格式化"""
        if seconds < 0:
            return "计算中..."
        
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        seconds = int(seconds % 60)
        
        if hours > 0:
            return f"{hours}小时{minutes}分钟"
        elif minutes > 0:
            return f"{minutes}分钟"
        else:
            return "1分钟"  # 不到1分钟也显示1分钟

    def process_single_file(self, file_path, target_dir):
        """处理单个文件"""
        try:
            # 获取文件时间
            file_time = self.get_file_time(file_path)
            if not file_time:
                raise ValueError("无法获取文件时间")
            
            # 获取件分类
            category = self.get_file_category(file_path)
            
            # 构建目标路径
            year = file_time.strftime("%Y")
            month = file_time.strftime("%m")
            filename = os.path.basename(file_path)
            
            # 构建目标目录
            if self.organize_by_month_var.get() == "month":
                if category == 'photos':
                    target_subdir = os.path.join(target_dir, year, month)
                else:
                    target_subdir = os.path.join(target_dir, year, month, category)
            else:
                if category == 'photos':
                    target_subdir = os.path.join(target_dir, year)
                else:
                    target_subdir = os.path.join(target_dir, year, category)
            
            # 检源文件是否已经在正确的位置
            current_dir = os.path.dirname(file_path)
            if os.path.normpath(current_dir) == os.path.normpath(target_subdir):
                self.logger.info(f"文件已在正确位置: {file_path}")
                return True  # 直接返回True，需要使用add方法
            
            # 确保目标目录存在
            os.makedirs(target_subdir, exist_ok=True)
            
            # 构建目标文路径
            target_path = os.path.join(target_subdir, filename)
            
            # 如果目标件已存在，添序号
            if os.path.exists(target_path):
                # 如果是相文件，跳过处理
                if os.path.samefile(file_path, target_path):
                    self.logger.info(f"跳过相同文件: {file_path}")
                    # 同样更新进度
                    self.progress_queue.put(("progress", self.processed_files / self.total_files * 100))
                    return True
                
                # 检查文件大小是否相同
                if os.path.getsize(file_path) == os.path.getsize(target_path):
                    self.logger.info(f"目标位置已存在相同大小的文件，跳过: {filename}")
                    # 更新进度
                    self.progress_queue.put(("progress", self.processed_files / self.total_files * 100))
                    return True
                
                # 如果文件不同，添加序号
                base, ext = os.path.splitext(filename)
                counter = 1
                while os.path.exists(target_path):
                    new_filename = f"{base}_{counter}{ext}"
                    target_path = os.path.join(target_subdir, new_filename)
                    counter += 1
            
            # 移动或复文件
            try:
                if self.move_files_var.get():
                    shutil.move(file_path, target_path)
                    self.logger.info(f"已移动: {filename} -> {target_path}")
                else:
                    shutil.copy2(file_path, target_path)
                    self.logger.info(f"已复制: {filename} -> {target_path}")
                return True  # 返回 True 表示处理成功
            
            except Exception as e:
                self.logger.error(f"处理文件失败 {file_path}: {str(e)}")
                raise
            
        except Exception as e:
            raise ValueError(f"文件操作失败: {str(e)}")

    def get_file_time(self, file_path):
        """获取文件的时间信息"""
        def is_valid_year(year):
            """检查年份是否有效（1970-2100）"""  # 修复"份"字
            return 1970 <= year <= 2100

        methods = []
        if self.time_method_vars[0].get():  # EXIF
            methods.append(self.get_exif_time)
        if self.time_method_vars[1].get():  # 文件名
            methods.append(self.get_filename_time)
        if self.time_method_vars[2].get():  # 修改时间
            methods.append(self.get_modified_time)
            
        for method in methods:
            try:
                time = method(file_path)
                if time and is_valid_year(time.year):
                    return time
            except:
                continue
                
        # 如果所有方都失败，使用当前时间
        self.logger.warning(f"无法获取有效的文件时间，用当时间: {file_path}")
        return datetime.now()

    def get_exif_time(self, file_path):
        """从EXIF信息获取间"""
        try:
            with Image.open(file_path) as img:
                exif = img._getexif()
                if exif:
                    for tag_id in [36867, 36868, 306]:  # DateTimeOriginal, DateTimeDigitized, DateTime
                        if tag_id in exif:
                            return datetime.strptime(exif[tag_id], '%Y:%m:%d %H:%M:%S')
        except:
            pass
        return None

    def get_filename_time(self, file_path):
        """从文件名获取时间"""  # 修复"获取"
        filename = os.path.basename(file_path)
        self.logger.info(f"开始解析文件名: {filename}")  # 修复"开始"
        
        # 先尝试匹配 YYYYMMDD 格式
        date_match = re.match(r'(\d{8}).*', filename)
        if date_match:
            try:
                date_str = date_match.group(1)
                year = int(date_str[:4])
                month = int(date_str[4:6])
                day = int(date_str[6:8])
                
                self.logger.info(f"从文件名取日期: {year}年{month}月{day}日")
                
                if 1970 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31:
                    return datetime(year, month, day)
            except (ValueError, IndexError) as e:
                self.logger.warning(f"日期解析失败: {str(e)}")
        
        # 如果上面的匹配失败，再尝试其他
        patterns = [
            r'(\d{4})[-_]?(\d{2})[-_]?(\d{2})',  # YYYY-MM-DD
            r'(\d{4})(\d{2})(\d{2})_\d{6}',      # 信格
            r'IMG_(\d{4})(\d{2})(\d{2})',        # 机格式
            r'Screenshot_(\d{4})(\d{2})(\d{2})'   # 截图格式
        ]
        
        for pattern in patterns:
            match = re.search(pattern, filename)
            if match:
                try:
                    groups = match.groups()
                    self.logger.info(f"匹配到模式: {pattern}, 分组: {groups}")  # 加调试日志
                    
                    if len(groups) == 1:
                        # 处理8位数字的 (YYYYMMDD)
                        date_str = groups[0]
                        year = int(date_str[:4])
                        month = int(date_str[4:6])
                        day = int(date_str[6:8])
                    else:
                        # 处理年月日分组的情况
                        year = int(groups[0])
                        month = int(groups[1])
                        day = int(groups[2])
                    
                    # 验证日的有效性
                    if 1970 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31:
                        result_date = datetime(year, month, day)
                        self.logger.info(f"成功解析日期: {result_date}")  # 加调试日志
                        return result_date
                    else:
                        self.logger.info(f"效的日期值: {year}-{month}-{day}")
                    
                except (ValueError, IndexError) as e:
                    self.logger.info(f"日期析失败: {str(e)}")
                    continue
        
        self.logger.info(f"无法从文件名解析日期: {filename}")  # 修复"解析"
        self.logger.info(f"无法从文件名解析日: {filename}")
        return None

    def get_modified_time(self, file_path):
        """获文件修改时间"""
        return datetime.fromtimestamp(os.path.getmtime(file_path))

    def is_valid_file(self, file_path):
        """检查是否为有效的图片文件"""
        try:
            if not os.path.isfile(file_path):
                self.logger.debug(f"是文件: {file_path}")
                return False
            
            if not file_path.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.heic')):
                self.logger.debug(f"是支持图片格式: {file_path}")
                return False
            
            file_size = os.path.getsize(file_path)
            if not (0 < file_size < 500 * 1024 * 1024):
                self.logger.debug(f"文件大小不符合要求: {file_path} ({file_size} bytes)")
                return False
            
            return True
        except Exception as e:
            self.logger.error(f"检查文件有效性时出错 {file_path}: {str(e)}")
            return False

    def load_settings(self):
        """加载设置"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    self.logger.info(f"成功加载配置: {settings}")
                    return settings
        except Exception as e:
            self.logger.error(f"加配置失败: {str(e)}")
        return {}

    def save_settings(self):
        """保存置"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=4)
            self.logger.info("配置已保存")
        except Exception as e:
            self.logger.error(f"保存配置失败: {str(e)}")

    def _apply_config_settings(self):
        """应用已加载的配置"""  # 修复"配置"
        try:
            settings = self.load_settings()
            if settings:
                # 设置源目录和目标目录
                if 'source_dir' in settings:
                    self.source_entry.delete(0, tk.END)
                    self.source_entry.insert(0, settings['source_dir'])
                if 'target_dir' in settings:
                    self.target_entry.delete(0, tk.END)
                    self.target_entry.insert(0, settings['target_dir'])
                
                # 设置其选项
                if 'move_files' in settings:
                    self.move_files_var.set(settings['move_files'])
                if 'include_subfolders' in settings:
                    self.include_subfolders_var.set(settings['include_subfolders'])
                if 'cleanup_enabled' in settings:
                    self.cleanup_enabled.set(settings['cleanup_enabled'])
                if 'check_duplicates' in settings:
                    self.check_duplicates_var.set(settings['check_duplicates'])
                if 'organize_by_month' in settings:
                    self.organize_by_month_var.set(settings['organize_by_month'])
                if 'time_methods' in settings:
                    for var, value in zip(self.time_method_vars, settings['time_methods']):
                        var.set(value)
                
                self.logger.info("已应用保存的配置")  # 修复"配置"
        except Exception as e:
            self.logger.error(f"应用配置失败: {str(e)}")  # 修复"配置"

    def on_closing(self):
        """窗口关闭时的处理"""
        try:
            # 只有当路径不为空时才保存
            settings = {
                'source_dir': self.source_entry.get().strip(),
                'target_dir': self.target_entry.get().strip(),
                'move_files': self.move_files_var.get(),
                'include_subfolders': self.include_subfolders_var.get(),
                'cleanup_enabled': self.cleanup_enabled.get(),
                'check_duplicates': self.check_duplicates_var.get(),
                'organize_by_month': self.organize_by_month_var.get(),
                'time_methods': [var.get() for var in self.time_method_vars]
            }
            
            # 只有当路径为空时才保存
            if settings['source_dir'] or settings['target_dir']:
                with open(self.config_file, 'w', encoding='utf-8') as f:
                    json.dump(settings, f, ensure_ascii=False, indent=4)
                self.logger.info(f"成功保存配置: {settings}")
        except Exception as e:
            self.logger.error(f"保存配置失败: {str(e)}")
        
        self.root.destroy()

    def on_organize_method_change(self, *args):
        """处理整理方式更"""
        is_by_month = bool(self.organize_by_month_var.get())
        self.logger.info(f"整理方已更改: {'按年月' if is_by_month else '仅按年'}")
        self.save_settings()

    def check_duplicate_files(self, target_dir):
        """查标目录中的重复文件"""
        try:
            self.logger.info("开检查重复文件...")
            self.progress_queue.put(("message", "开始检查重复文件..."))
            
            # 用字典存储件大小内容的哈值
            file_dict = {}  # {(size, hash): [file_paths]}
            total_files = 0
            duplicate_count = 0
            
            # 历目标目录
            for root, _, files in os.walk(target_dir):
                total_files += len(files)
                
            processed = 0
            
            for root, _, files in os.walk(target_dir):
                for filename in files:
                    if not self.running:
                        return
                        
                    file_path = os.path.join(root, filename)
                    try:
                        # 获文件大小
                        file_size = os.path.getsize(file_path)
                        
                        # 计算文件希值只读前8KB提高速度）
                        with open(file_path, 'rb') as f:
                            file_hash = hash(f.read(8192))
                        
                        # 使用文件大小和哈值作键
                        key = (file_size, file_hash)
                        
                        if key in file_dict:
                            file_dict[key].append(file_path)
                            duplicate_count += 1
                        else:
                            file_dict[key] = [file_path]
                            
                        processed += 1
                        progress = (processed / total_files) * 100
                        self.progress_queue.put(("progress", progress))
                        
                    except Exception as e:
                        self.logger.error(f"处理文件失败 {file_path}: {str(e)}")
                        continue
            
            # 处理重复
            if duplicate_count > 0:
                self.logger.info(f"发现 {duplicate_count} 个重复文件")
                self.progress_queue.put(("message", f"现 {duplicate_count} 个重复文件"))
                
                for key, file_paths in file_dict.items():
                    if len(file_paths) > 1:
                        # 保留最新的文件
                        newest_file = max(file_paths, key=os.path.getctime)
                        file_paths.remove(newest_file)
                        
                        # 删除其他重复文件
                        for file_path in file_paths:
                            try:
                                os.remove(file_path)
                                self.logger.info(f"删重文件: {file_path}")
                                self.progress_queue.put(("message", f"删除重复文件: {os.path.basename(file_path)}"))
                            except Exception as e:
                                self.logger.error(f"删除文件失败 {file_path}: {str(e)}")
            
            self.progress_queue.put(("message", "重复文件检查完成"))
            self.logger.info("重复文件检查完成")
            
        except Exception as e:
            self.logger.error(f"检查重复文件时出错: {str(e)}")
            self.progress_queue.put(("message", f"检查重复文件时错: {str(e)}"))

    def cleanup_empty_dirs(self, target_dir):
        """清理空目录无效目录"""
        try:
            self.logger.info("开始清理目录...")
            self.progress_queue.put(("message", "开清目录..."))
            
            # 要删除的特殊文件/目录模式
            special_patterns = [
                '.DS_Store',      # Mac系统文件
                'Thumbs.db',      # Windows缩略图文件
                '._.DS_Store',    # Mac元数
                '._*',            # Mac隐藏文件
                'desktop.ini',    # Windows面置文件
                '.spotlight*',    # Mac Spotlight索引
                '.fseventsd',     # Mac文件系事件
                '.Trashes'        # Mac收
            ]
            
            cleaned_count = 0
            
            # 从下往上遍历目录（先处理子目录）
            for root, dirs, files in os.walk(target_dir, topdown=False):
                # 删除特殊文件
                for file in files:
                    file_path = os.path.join(root, file)
                    # 检查是否配特殊件模式
                    if any(fnmatch.fnmatch(file.lower(), pattern.lower()) for pattern in special_patterns):
                        try:
                            os.remove(file_path)
                            self.logger.info(f"删除特文件: {file_path}")
                            cleaned_count += 1
                        except Exception as e:
                            self.logger.error(f"删除文件失败 {file_path}: {str(e)}")
                
                # 检查目录是否为空或只包含特殊文件
                try:
                    # 重获取目录内容（因可能已删除了些文件）
                    remaining_files = [f for f in os.listdir(root) 
                                     if not any(fnmatch.fnmatch(f.lower(), p.lower()) 
                                              for p in special_patterns)]
                    
                    # 如果目录为空或包含特件
                    if not remaining_files:
                        # 保不目标根目录
                        if root != target_dir:
                            try:
                                # 除有剩内容并删除目录
                                shutil.rmtree(root)
                                self.logger.info(f"删除空目录: {root}")
                                cleaned_count += 1
                            except Exception as e:
                                self.logger.error(f"删除目录失败 {root}: {str(e)}")
                
                except Exception as e:
                    self.logger.error(f"处理目录失败 {root}: {str(e)}")
            
            self.logger.info(f"清理成，共清理 {cleaned_count} 个项目")
            self.progress_queue.put(("message", f"清理完成，共清理 {cleaned_count} 个项目"))
            
        except Exception as e:
            self.logger.error(f"清理过出错: {str(e)}")
            self.progress_queue.put(("message", f"清理错误: {str(e)}"))

    def clear_log(self):
        """清理日志内容"""
        try:
            # 临时禁用文本框更新以避免闪烁
            self.log_text.configure(state='disabled')
            
            # 清空日志文本框
            self.log_text.delete(1.0, tk.END)
            
            # 重置进度条和状态显示
            self.progress_var.set(0)
            self.progress_status.configure(text="已完成: 0/0")
            self.progress_percent.configure(text="0%")
            self.status_label.configure(text="准备就绪")
            
            # 确保滚动条隐藏
            self.v_scrollbar.grid_remove()
            self.h_scrollbar.grid_remove()
            
            # 重新启用文本框
            self.log_text.configure(state='normal')
            
            # 添加清理完成的消息
            self.log_message("日志已清理")
            
            # 强制更新布局
            self.log_text.update_idletasks()
            
        except Exception as e:
            self.logger.error(f"清理日志失败: {str(e)}")

    def update_scrollbar_y(self, *args):
        """更新垂直滚动条"""
        self.v_scrollbar.set(*args)
        # 当内不需要滚动时隐藏滚动条
        if float(args[1]) >= 1.0:
            self.v_scrollbar.grid_remove()
        else:
            self.v_scrollbar.grid()

    def update_scrollbar_x(self, *args):
        """更水滚动条"""
        self.h_scrollbar.set(*args)
        # 当内容不需要滚动时隐藏滚动条
        if float(args[1]) >= 1.0:
            self.h_scrollbar.grid_remove()
        else:
            self.h_scrollbar.grid()

    def get_system_font(self):
        """获取系统默认字体"""
        try:
            # 获取当前默认字体
            default_font = tkfont.nametofont("TkDefaultFont")
            font_name = default_font.actual()['family']
            
            # 如果在 Windows 上没有字体，使用微软雅黑
            if sys.platform == 'win32' and (not font_name or font_name == 'TkDefaultFont'):
                font_name = "Microsoft YaHei UI"
            
            self.logger.info(f"系统默认字体: {font_name}")
            return font_name
        except Exception as e:
            self.logger.error(f"获取系统字体失败: {str(e)}")
            return "Microsoft YaHei UI" if sys.platform == 'win32' else ""

    def clear_config(self):
        """清除配置并重置为默认值"""
        if messagebox.askyesno("确认", "确定要重置所有配置吗？\n这将会清除所有保存的设置。"):
            try:
                # 删除配置文件
                if os.path.exists(self.config_file):
                    os.remove(self.config_file)
                    self.logger.info("已删除配置文件")
                
                # 重置所有控件状态为默认值
                self.organize_by_month_var.set("month")
                self.move_files_var.set(False)
                self.include_subfolders_var.set(True)
                self.cleanup_enabled.set(True)
                self.check_duplicates_var.set(True)
                
                # 重置时间获取方式
                for var in self.time_method_vars:
                    var.set(True)
                
                # 清空路径
                self.source_entry.delete(0, tk.END)
                self.target_entry.delete(0, tk.END)
                
                # 重置进度条和状态显示
                self.progress_var.set(0)
                self.progress_status.configure(text="已完成: 0/0")
                self.progress_percent.configure(text="0%")
                self.status_label.configure(text="准备就绪")
                
                # 重置按钮状态
                self.start_button.configure(state=tk.NORMAL)
                self.stop_button.configure(state=tk.DISABLED)
                
                # 清空日志文本框
                self.log_text.delete(1.0, tk.END)
                
                # 重置处理计数器
                self.total_files = 0
                self.processed_files = 0
                self.skipped_files = 0
                self.duplicate_files = 0
                self.cleaned_dirs = 0
                self.error_files = []
                
                # 重新加载默认设置
                self.settings = self.load_settings()
                
                self.log_message("配置已重置为默认值")
                
            except Exception as e:
                self.logger.error(f"重置配置失败: {str(e)}")
                self.log_message(f"重置配置失败: {str(e)}", level='error')

    def get_organize_by_month(self):
        """获取是否按月整理的态"""
        return self.organize_by_month_var.get() == "month"

    def create_log_text(self, parent):
        """创建日志文本区域"""
        # 创建主框架
        text_frame = ttk.Frame(parent, style='Card.TFrame')
        text_frame.pack(fill=tk.X, pady=self.scaled(5))  # 减小上下边距
        
        # 设置最小高度
        text_frame.pack_propagate(False)
        text_frame.configure(height=self.scaled(80))  # 固定高度
        
        # 创建内部框架
        text_inner = ttk.Frame(text_frame, style='Card.TFrame')
        text_inner.pack(fill=tk.BOTH, expand=True, padx=self.scaled(15))
        
        # 创建文本框
        self.log_text = tk.Text(
            text_inner,
            font=self.fonts['body'],
            wrap=tk.WORD,
            relief='flat',
            bg=self.colors['bg_light'],
            height=3,  # 固定为3行
            padx=self.scaled(5),
            pady=self.scaled(3)
        )
        
        # 设置文本标签样式
        self.log_text.tag_configure('error', 
            foreground=self.colors['error'],
            spacing1=self.scaled(2))
        self.log_text.tag_configure('warning',
            foreground=self.colors['warning'],
            spacing1=self.scaled(2))
        self.log_text.tag_configure('info',
            foreground=self.colors['text'],
            spacing1=self.scaled(2))
        self.log_text.tag_configure('skip',
            foreground=self.colors['text_secondary'],
            spacing1=self.scaled(2))
        
        # 创建滚动条
        self.v_scrollbar = ttk.Scrollbar(text_inner, orient="vertical", command=self.log_text.yview)
        self.h_scrollbar = ttk.Scrollbar(text_inner, orient="horizontal", command=self.log_text.xview)
        
        # 配置文本框的滚动
        self.log_text.configure(
            yscrollcommand=self.update_scrollbar_y,
            xscrollcommand=self.update_scrollbar_x
        )
        
        # 使用网格布局
        self.log_text.grid(row=0, column=0, sticky="nsew")
        self.v_scrollbar.grid(row=0, column=1, sticky="ns")
        self.h_scrollbar.grid(row=1, column=0, sticky="ew")
        
        # 配置网格权重
        text_inner.grid_rowconfigure(0, weight=1)
        text_inner.grid_columnconfigure(0, weight=1)
        
        # 初始化时隐藏滚动条
        self.v_scrollbar.grid_remove()
        self.h_scrollbar.grid_remove()

    def open_log_file(self):
        """打开日志文件"""
        try:
            # 获取当日志文件路径
            log_dir = os.path.join(os.path.expanduser("~"), ".photo_organizer", "logs")
            current_log = os.path.join(log_dir, f"photo_organizer_{datetime.now().strftime('%Y%m%d')}.log")
            
            if os.path.exists(current_log):
                # Windows系统
                if sys.platform == 'win32':
                    os.startfile(current_log)
                # macOS系统
                elif sys.platform == 'darwin':
                    subprocess.run(['open', current_log])
                # Linux系统
                else:
                    subprocess.run(['xdg-open', current_log])
                
                self.log_message("已打开日志文件")
            else:
                messagebox.showinfo("提", "前没有日志文")
                
        except Exception as e:
            self.log_message(f"打开日志文件失败: {str(e)}", level='error')
            messagebox.showerror("错误", f"无法打开日志文件: {str(e)}")

    def show_changelog(self):
        """显示版本说明"""
        changelog = """照片整理助手 v1.0.2

主要功能：
• 按年/月自动整理照片和视频
• 支持 EXIF、文件名、修改时间多种时间获取方式
• 支持移动或复制文件
• 自动检测重复文件
• 支持清理空目录
• 支持子目录递归处理
• 支持常见图片和视频格式

更新说明：
[v1.0.2] 2024.03.17
- 优化界面布局和视觉体验
- 改进性能监控和资源管理
- 优化日志显示和文件处理逻辑
- 修复已知问题和提升稳定性

[v1.0.1] 2024.02.28
- 添加多线程支持,提升处理速度
- 优化内存使用和批处理机制
- 改进文件时间获取算法
- 增强重复文件检测功能
- 完善错误处理和日志记录

[v1.0.0] 2024.02.15
- 首次发布
- 实现基础文件整理功能
- 支持多种时间获取方式
- 提供现代化图形界面
- 支持配置保存和加载"""

        # 创建对话框
        dialog = tk.Toplevel(self.root)
        dialog.title("更新日志与说明")
        
        # 设置模态
        dialog.transient(self.root)
        dialog.grab_set()
        
        # 设置对话框大小和位置
        dialog_width = 800
        dialog_height = 680
        x = (dialog.winfo_screenwidth() - dialog_width) // 2
        y = (dialog.winfo_screenheight() - dialog_height) // 2
        dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")
        
        # 主框架
        main_frame = ttk.Frame(dialog, style='Card.TFrame')
        main_frame.pack(fill=tk.BOTH, expand=True, padx=35, pady=30)
        
        # 文本框
        text = tk.Text(main_frame,
                      wrap=tk.WORD,  # 启用自动换行
                      font=(self.get_system_font(), self.scaled(10)),
                      relief='flat',
                      bg=self.colors['bg_light'],
                      padx=30,
                      pady=25)
        text.pack(fill=tk.BOTH, expand=True)
        
        # 添加样式标签
        text.tag_configure('title', 
                          font=(self.get_system_font(), self.scaled(14), 'bold'),
                          spacing1=self.scaled(10),
                          spacing3=self.scaled(10))
        
        text.tag_configure('heading',
                          font=(self.get_system_font(), self.scaled(12), 'bold'),
                          spacing1=self.scaled(10),
                          spacing3=self.scaled(5))
        
        text.tag_configure('version',
                          font=(self.get_system_font(), self.scaled(11), 'bold'),
                          spacing1=self.scaled(8),
                          spacing3=self.scaled(4))
        
        # 设置文本内容并应用样式
        text.insert('1.0', changelog)
        
        # 应用样式标签
        text.tag_add('title', '1.0', '1.end')  # 标题
        
        # 为"主要功能："、"使用说明："和"更新说明："添加样式
        for heading in ['主要功能：', '使用说明：', '更新说明：']:
            start = text.search(heading, '1.0', tk.END)
            if start:
                end = f"{start}+{len(heading)}c"
                text.tag_add('heading', start, end)
        
        # 为版本号添加样式
        for version in ['[v1.0.2]', '[v1.0.1]', '[v1.0.0]']:
            start = '1.0'
            while True:
                start = text.search(version, start, tk.END)
                if not start:
                    break
                end = f"{start}+{len(version)}c"
                text.tag_add('version', start, end)
                start = end
        
        text.configure(state='disabled')  # 设为只读
        
        # 添加滚动条
        scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        text.configure(yscrollcommand=scrollbar.set)
        
        # 添加确定按钮
        button_frame = ttk.Frame(dialog, style='Card.TFrame')
        button_frame.pack(pady=15)
        
        ttk.Button(button_frame,
                   text="确定",
                   command=dialog.destroy,
                   width=8,
                   style='Primary.TButton').pack()

    def _get_config_path(self):
        """获取配置文件路径"""
        if getattr(sys, 'frozen', False):
            # PyInstaller创建的exe
            return os.path.join(sys._MEIPASS, 'config.json')
        else:
            # 开发环境
            return 'config.json'
    
    def _load_config(self):
        """加载配置文件"""
        try:
            with open(self._get_config_path(), 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"加载配置失败: {e}")
            return {}
    
    def _apply_config_settings(self):
        """应用配置"""
        default_settings = self.config.get('default_settings', {})
        
        # 应用默认设置
        self.move_files_var.set(default_settings.get('move_files', False))
        self.include_subfolders_var.set(default_settings.get('include_subfolders', True))
        self.cleanup_enabled.set(default_settings.get('cleanup_enabled', True))
        self.check_duplicates_var.set(default_settings.get('check_duplicates', True))
        self.organize_by_month_var.set(default_settings.get('organize_by_month', 'month'))
        # ... 其他设置

    def get_file_category(self, file_path):
        """获取文件分类"""
        filename = os.path.basename(file_path).lower()
        
        # 定义文件类型模式
        patterns = {
            'screenshots': [
                r'^screenshot[_-]',      # Screenshot开头
                r'截图',
                r'屏幕截图',
                r'snipaste',
                r'capture',
                r'snip',
                r'lightshot',
                r'screen\s*shot',
                r'截屏',
                r'快照',
            ],
            'others': [                 
                r'^\d{13}-[a-zA-Z0-9_]+',
                r'信图片',
                r'wx_camera',
                r'mmexport',
                r'img_[0-9]{13}',
                r'weixin',
                r'qq',
                r'edit',
                r'modified',
                r'(copy)',
                r'副本',
                r'修改',
            ]
        }
        
        # 检查文件名是否匹配任何模式
        for category, pattern_list in patterns.items():
            for pattern in pattern_list:
                if re.search(pattern, filename, re.IGNORECASE):
                    return category
        
        # 尝试通过EXIF判断是否为相机照片（仅对图片文件）
        try:
            with Image.open(file_path) as img:
                exif = img._getexif()
                if exif and (271 in exif or 272 in exif):  # 检查制造商或型号
                    return 'photos'
        except:
            pass
        
        # 默认返回 photos 类别
        return 'photos'

    def get_optimal_config(self):
        """取优化配置"""  # 修复"配置"
        try:
            # 获取系统信息
            cpu_count = multiprocessing.cpu_count()
            memory = psutil.virtual_memory()
            
            # 根据CPU和内存动态调
            if cpu_count >= 8:
                max_workers = min(cpu_count // 2, 8)
                batch_size = 100
            else:
                max_workers = max(2, cpu_count - 1)
                batch_size = 50
                
            # 根据可用内存调整
            available_gb = memory.available / (1024 * 1024 * 1024)
            if available_gb < 4:
                max_workers = min(max_workers, 2)
                batch_size = 30
            
            # 检查CPU使用率
            cpu_percent = psutil.cpu_percent(interval=1)
            if cpu_percent > 70:  # CPU负载较高
                max_workers = max(1, max_workers - 1)  # 减少线程数
                batch_size = max(20, batch_size // 2)  # 减批处理大小
            
            self.logger.info(f"系统配置 - CPU核心: {cpu_count}, "  # 修复"系统配置"
                            f"可用内存: {available_gb:.1f}GB, "
                            f"CPU使用率: {cpu_percent}%, "
                            f"优化配置 - 线程数: {max_workers}, "  # 修复"优化配置"
                            f"批处理大小: {batch_size}")
            
            return max_workers, batch_size
            
        except Exception as e:
            self.logger.error(f"获取系统配置失败: {str(e)}")  # 修复"配置"
            return 2, 30  # 使用更保守的默认值

    def get_all_files(self, source_dir):
        """获取所有需要处理的文件"""
        try:
            all_files = []
            total_size = 0
            start_time = time.time()
            
            # 支持的文件类型
            supported_extensions = {
                '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.heic', '.raw', '.cr2', '.nef', '.arw',  # 图片格式
                '.mp4', '.mov', '.avi', '.mkv', '.wmv', '.m4v', '.3gp'  # 视频格式
            }
            
            # 使用 os.walk 快速扫描
            if self.include_subfolders_var.get():
                for root, _, files in os.walk(source_dir):
                    for filename in files:
                        ext = os.path.splitext(filename.lower())[1]
                        if ext in supported_extensions:  # 统一判断所有支持的格式
                            file_path = os.path.join(root, filename)
                            all_files.append(file_path)
                            
                            # 每1000个文件更新一次状
                            if len(all_files) % 1000 == 0:
                                elapsed = time.time() - start_time
                                speed = len(all_files) / elapsed if elapsed > 0 else 0
                                self.progress_queue.put(("status", 
                                    f"正在扫描文件... 已找到 {len(all_files)} 个文件 ({speed:.0f} 文件/秒)"))
            else:
                # 仅扫描根目录
                with os.scandir(source_dir) as entries:
                    for entry in entries:
                        if entry.is_file():
                            ext = os.path.splitext(entry.name.lower())[1]
                            if ext in supported_extensions:  # 统一判断所有支持的格式
                                all_files.append(entry.path)
            
            return all_files
            
        except Exception as e:
            self.logger.error(f"扫描文件时出错: {str(e)}", exc_info=True)
            raise

    def monitor_system_resources(self):
        """监控系统资源使用情况"""
        try:
            # 获取系统信息
            cpu_count = psutil.cpu_count()
            memory = psutil.virtual_memory()
            cpu_percent = psutil.cpu_percent()
            available_memory = f"{memory.available / (1024**3):.1f}GB"
            
            # 记录系统配置和资源使用情况
            self.logger.info(
                f"系统配置 - CPU核心: {cpu_count}, "
                f"可用内存: {available_memory}, "
                f"CPU使用率: {cpu_percent}%, "
                f"优化配置 - 线程数: {self.max_workers}, "
                f"批处理大小: {self.batch_size}"
            )
            
            # 定期检查系统资源
            if self.running:
                self._adjust_batch_size()
                # 每30秒检查一次系统资源
                self.root.after(30000, self.monitor_system_resources)
                
        except Exception as e:
            self.logger.error(f"控系统资源失败: {str(e)}")

    def _process_batch(self, batch, target_dir):
        """优化的批处理"""
        results = []
        batch_size = len(batch)
        
        for i, file_path in enumerate(batch):
            if not self.running:
                break
                
            try:
                result = self.process_single_file(file_path, target_dir)
                if result == True:
                    results.append((file_path, True, "skipped"))
                else:
                    results.append((file_path, True, None))
                
            except Exception as e:
                self.logger.error(f"处理文件失败 {file_path}: {str(e)}", exc_info=True)
                results.append((file_path, False, str(e)))
        
        return results

    def _optimize_system_resources(self):
        """智能优化系统资源配置"""
        try:
            # 获取系统详细信息
            cpu_count = psutil.cpu_count(logical=True)  # 逻辑CPU核心数
            total_memory = psutil.virtual_memory().total / (1024 * 1024 * 1024)  # 总内存(GB)
            available_memory = psutil.virtual_memory().available / (1024 * 1024 * 1024)  # 可用内存(GB)
            cpu_percent = psutil.cpu_percent()
            
            # 智能计算线程数
            # 保留至少1个核心给系统，但不超过16个线程
            suggested_threads = max(2, min(cpu_count - 1, 16))
            
            # 智能计算批处理大小
            # 基础批处理大小：每GB可用内存20个文件，但不少于50个
            base_batch_size = max(50, int(available_memory * 20))
            
            # 根据系统配置确定最终参数
            self.thread_count = suggested_threads
            self.batch_size = min(2000, base_batch_size)  # 不超过2000
            self.max_batch_size = min(5000, int(base_batch_size * 2))  # 最大不超过5000
            self.batch_increment = max(20, min(200, int(base_batch_size * 0.1)))  # 增量为当前大小的10%
            
            # 记录系统配置和优化参数
            self.logger.info(
                f"系统配置 - CPU核心: {cpu_count}, "
                f"可用内存: {available_memory:.1f}GB, "
                f"CPU使用率: {cpu_percent}%, "
                f"优化配置 - 线程数: {self.thread_count}, "
                f"批处理大小: {self.batch_size}"
            )
            
            # 记录详细配置
            self.logger.debug(
                f"详细配置 - 最大批处理: {self.max_batch_size}, "
                f"批次增量: {self.batch_increment}, "
                f"基础批次: {base_batch_size}"
            )
            
            return True
            
        except Exception as e:
            self.logger.error(f"系统资源优化失败: {str(e)}")
            # 使用保守的默认值
            self.thread_count = 2
            self.batch_size = 50
            self.max_batch_size = 200
            self.batch_increment = 20
            return False

    def update_status(self, status_type):
        """更新状态显示"""
        if status_type == "scanning":
            self.status_label.configure(text="准备就绪 - 正在扫描文件...")
        elif status_type == "processing":
            self.status_label.configure(text="准备就绪 - 正在处理文件...")
        elif status_type == "ready":
            self.status_label.configure(text="准备就绪")
        # ... 其他状态处理 ...

    def show_welcome(self, auto_show=False):
        """显示欢迎说明
        
        Args:
            auto_show (bool): 是否是自动显示。如果是自动显示且非首次运行，则不显示
        """
        # 如果是自动显示且已经不是首次运行，则不显示
        if auto_show and not self.settings.get('first_run', True):
            return
        
        dialog = tk.Toplevel(self.root)
        dialog.title("欢迎使用")
        
        # 设置对话框大小和位置
        dialog_width = 800
        dialog_height = 680
        x = (dialog.winfo_screenwidth() - dialog_width) // 2
        y = (dialog.winfo_screenheight() - dialog_height) // 2
        dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")
        
        dialog.transient(self.root)
        dialog.grab_set()
        
        # 主框架
        main_frame = ttk.Frame(dialog, style='Card.TFrame')
        main_frame.pack(fill=tk.BOTH, expand=True, padx=35, pady=30)
        
        # 文本框
        text = tk.Text(main_frame,
                      wrap=tk.WORD,
                      font=(self.get_system_font(), self.scaled(11)),
                      relief='flat',
                      bg=self.colors['bg_light'],
                      padx=30,
                      pady=25)
        text.pack(fill=tk.BOTH, expand=True)
        
        # 样式签
        text.tag_configure('heading',
                          font=(self.get_system_font(), self.scaled(12), 'bold'),
                          foreground=self.colors['primary'])
        
        welcome_text = """欢迎使用照片整理助手！

主要功能：
• 按年/月自动整理照片和视频
• 支持 EXIF、文件名、修改时间多种时间获取方式
• 支持移动或复制文件
• 自动检测重复文件
• 支持清理空目录
• 支持子目录递归处理
• 支持常见图片和视频格式

使用说明：
1. 选择需要整理的源文件夹
2. 选择整理后的目标文件夹  
3. 根据需要调整整理选项
4. 点击"开始整理"即可

注意事项：
• 建议先使用"复制"模式测试
• 整理前请确保文件已备份
• 可以随时点击"停止"暂停处理
"""
        
        # 设置文本内容
        text.insert('1.0', welcome_text)
        text.configure(state='disabled')  # 设为只读
        
        # 底部按框架
        button_frame = ttk.Frame(dialog, style='Card.TFrame')
        button_frame.pack(pady=15)
        
        # 确定按钮
        ttk.Button(button_frame,
                   text="确定",
                   command=dialog.destroy,
                   width=8,
                   style='Primary.TButton').pack()

    def save_welcome_preference(self, show_welcome):
        """保存欢迎弹窗显示偏好"""
        try:
            settings = self.load_settings()
            settings['show_welcome'] = show_welcome
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=4)
        except Exception as e:
            self.logger.error(f"保存欢迎弹窗偏好失败: {str(e)}")

    def open_directory(self, path):
        """打开指定目录"""
        try:
            if sys.platform == 'win32':
                os.startfile(path)
            elif sys.platform == 'darwin':  # macOS
                subprocess.run(['open', path])
            else:  # linux
                subprocess.run(['xdg-open', path])
        except Exception as e:
            self.logger.error(f"打开目录失败: {str(e)}")

if __name__ == "__main__":
    # 在创建窗口前设置DPI感知
    try:
        from ctypes import windll
        # 确保在Windows上正确设置DPI感知
        windll.user32.SetProcessDPIAware()
        windll.shcore.SetProcessDpiAwareness(1)
    except:
        pass

    root = tk.Tk()
    
    # 手动置缩放
    try:
        dpi = root.winfo_fpixels('1i')
        scale_factor = dpi / 96.0
        root.tk.call('tk', 'scaling', scale_factor)
    except:
        pass
    
    app = PhotoOrganizerGUI(root)
    
    # 绑定窗口关闭事件
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    
    # 更新所有待处理的GUI任务
    root.update_idletasks()
    
    # 设置初始最小尺寸
    root.minsize(app.scaled(800), app.scaled(600))
    
    # 获取窗口自然大小
    natural_width = max(root.winfo_reqwidth(), app.scaled(800))
    natural_height = max(root.winfo_reqheight(), app.scaled(600))
    
    # 获取屏幕尺寸
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    
    # 计算窗口位置使其居中
    x = (screen_width - natural_width) // 2
    y = (screen_height - natural_height) // 2
    
    # 设置窗口位置和大小
    root.geometry(f"{natural_width}x{natural_height}+{x}+{y}")
    
    root.mainloop()