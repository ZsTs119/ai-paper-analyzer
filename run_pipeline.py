#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一键流水线脚本 - 完整论文分析流程
功能：按顺序执行 Basic → Advanced 分析，默认今天，支持狂暴模式
"""
import os
import sys
import subprocess
import argparse
from datetime import datetime
from pathlib import Path

# 设置输出编码
if sys.platform == "win32":
    import codecs
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.detach())

class PipelineRunner:
    def __init__(self):
        self.success_steps = []
        self.failed_steps = []
        
    def run_command(self, cmd, step_name):
        """执行命令并处理结果"""
        print(f"🔄 执行{step_name}: {' '.join(cmd)}")
        print(f"{'='*60}")
        
        try:
            # 实时显示输出
            result = subprocess.run(cmd, text=True)
            
            if result.returncode == 0:
                print(f"✅ {step_name}完成")
                self.success_steps.append(step_name)
                return True
            else:
                print(f"❌ {step_name}失败 (退出码: {result.returncode})")
                self.failed_steps.append(step_name)
                return False
                
        except Exception as e:
            print(f"❌ {step_name}异常: {e}")
            self.failed_steps.append(step_name)
            return False
    
    def run_pipeline(self, date, rage_mode=False, silent=False):
        """运行完整流水线"""
        print(f"🚀 开始一键流水线分析")
        print(f"📅 分析日期: {date}")
        if rage_mode:
            print(f"🔥 狂暴模式: 已启用 (5并发极速处理)")
        if silent:
            print(f"🔇 静默模式: 已启用")
        print(f"{'='*60}")
        
        # 步骤1: Basic 分析
        print(f"\n📋 步骤1: Basic 基础分析")
        basic_cmd = [sys.executable, "run.py", "basic", date]
        if rage_mode:
            basic_cmd.append("--rageMode")
        if silent:
            basic_cmd.append("--silent")
            
        basic_success = self.run_command(basic_cmd, "Basic分析")
        
        if not basic_success:
            print(f"\n❌ Basic分析失败，终止流水线")
            self.print_summary()
            return False
        
        # 步骤2: Advanced 分析
        print(f"\n📋 步骤2: Advanced 智能分类")
        advanced_cmd = [sys.executable, "run.py", "advanced", date]
        if rage_mode:
            advanced_cmd.append("--rageMode")
        if silent:
            advanced_cmd.append("--silent")
            
        advanced_success = self.run_command(advanced_cmd, "Advanced分析")
        
        # 显示最终结果
        self.print_summary()
        return basic_success and advanced_success
    
    def print_summary(self):
        """显示执行摘要"""
        print(f"\n{'='*60}")
        print(f"📊 流水线执行摘要")
        print(f"{'='*60}")
        
        if self.success_steps:
            print(f"✅ 成功步骤: {', '.join(self.success_steps)}")
        
        if self.failed_steps:
            print(f"❌ 失败步骤: {', '.join(self.failed_steps)}")
        
        if len(self.success_steps) == 2:
            print(f"🎉 流水线完成！所有步骤执行成功")
        elif len(self.success_steps) == 1:
            print(f"⚠️  流水线部分完成，请检查失败步骤")
        else:
            print(f"💥 流水线失败，请检查配置和网络")

def validate_date_format(date_str):
    """验证日期格式"""
    try:
        datetime.strptime(date_str, '%Y-%m-%d')
        return True
    except ValueError:
        return False

def main():
    parser = argparse.ArgumentParser(
        description="""
🚀 一键流水线分析 (Pipeline Analysis)

功能说明:
  • 按顺序执行 Basic → Advanced 完整分析流程
  • 默认分析今天的论文数据
  • 支持狂暴模式，5并发极速处理
  • 自动处理步骤依赖，失败时智能终止

处理流程:
  1. Basic分析 - 获取、清洗、AI分析论文数据
  2. Advanced分析 - 智能分类、生成汇总报告

适用场景:
  • 日常一键获取最新论文分析
  • 快速处理指定日期的完整分析
  • 新手用户的简化操作入口
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
📋 使用示例:

🔹 基础用法:
  python run_pipeline.py                    # 分析今天的论文
  python run_pipeline.py 2024-05-15        # 分析指定日期
  python run_pipeline.py --silent          # 静默模式分析今天

🔥 狂暴模式:
  python run_pipeline.py --rageMode        # 狂暴模式分析今天
  python run_pipeline.py 2024-05-15 --rageMode  # 狂暴模式分析指定日期
  python run_pipeline.py --rageMode --silent     # 狂暴+静默模式

⚡ 性能对比:
  • 普通模式: Basic(3分钟) + Advanced(2分钟) = 5分钟
  • 🔥狂暴模式: Basic(34秒) + Advanced(45秒) = 1分20秒

💡 其他选择:
  • 单独执行: python run.py basic/advanced [date] [--rageMode]
  • 批量处理: python tools/batch_processor.py pipeline --start DATE --end DATE
  • 图形界面: python run_gui.py

⚠️  注意事项:
  • 狂暴模式需要稳定网络和充足API余额
  • Advanced分析依赖Basic分析结果
  • 日期格式必须为 YYYY-MM-DD
        """
    )
    
    parser.add_argument(
        'date',
        nargs='?',
        default=datetime.now().strftime('%Y-%m-%d'),
        help='分析日期 (YYYY-MM-DD格式)，默认为今天'
    )
    parser.add_argument(
        '--rageMode',
        action='store_true',
        help='🔥 狂暴模式：启用5并发处理，Basic+Advanced总耗时约1分20秒'
    )
    parser.add_argument(
        '--silent',
        action='store_true',
        help='静默模式，减少输出信息'
    )
    
    args = parser.parse_args()
    
    # 验证日期格式
    if not validate_date_format(args.date):
        print(f"❌ 无效的日期格式: {args.date}")
        print(f"💡 请使用 YYYY-MM-DD 格式，例如: 2024-05-15")
        return 1
    
    # 检查主脚本是否存在
    if not Path("run.py").exists():
        print(f"❌ 找不到主脚本 run.py")
        print(f"💡 请确保在项目根目录下运行此脚本")
        return 1
    
    # 运行流水线
    runner = PipelineRunner()
    success = runner.run_pipeline(args.date, args.rageMode, args.silent)
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())