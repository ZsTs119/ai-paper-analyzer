"""
AI分析器模块
负责使用AI分析论文内容并生成结构化摘要
"""
import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Optional
from pathlib import Path

from ..utils.console import ConsoleOutput
from ..utils.logger import get_logger
from ..utils.file_utils import FileManager
from ..utils.progress import ProgressManager
from ..utils.ai_client import create_retryable_client
from ..models.paper import Paper
from ..models.report import AnalysisResult, DailyReport
from .parser import ContentParser


class PaperAnalyzer:
    """
    论文AI分析器
    
    负责使用AI分析论文内容，生成结构化的分析结果
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化分析器
        
        Args:
            config: 配置字典
        """
        self.config = config
        self.console = ConsoleOutput()
        self.logger = get_logger('analyzer')
        self.file_manager = FileManager('analyzer')
        self.parser = ContentParser()
        
        # 设置默认配置
        self.output_dir = config.get('output_dir', 'data/daily_reports')
        self.ai_model = config.get('ai_model', 'zhipu')
        self.use_ai = config.get('use_ai', True)
        self.max_retries = config.get('max_retries', 3)
        self.retry_delay = config.get('retry_delay', 2)
        
        # 初始化AI客户端
        self.ai_client = None
        if self.use_ai:
            try:
                self.ai_client = create_retryable_client(
                    self.ai_model,
                    max_retries=self.max_retries
                )
            except Exception as e:
                self.logger.warning(f"AI客户端初始化失败: {e}")
                self.use_ai = False
    
    def analyze_batch(self, papers: List[Paper], date: str = None, silent: bool = False) -> List[AnalysisResult]:
        """
        批量分析论文
        
        Args:
            papers: 论文列表
            date: 日期字符串（用于保存结果）
            silent: 是否静默模式
            
        Returns:
            分析结果列表
        """
        if not papers:
            if not silent:
                self.console.print_warning("没有论文需要分析")
            return []
        
        if not silent:
            self.console.print_header("AI分析生成摘要", 3)
            self.console.print_info(f"开始顺序处理 {len(papers)} 篇论文")
        
        self.logger.info(f"开始批量分析 {len(papers)} 篇论文")
        
        # 初始化进度管理器
        progress = ProgressManager(len(papers), "AI分析论文") if not silent else None
        results = []
        
        # 准备输出文件（如果提供了日期）
        final_file = None
        if date:
            final_dir = Path(self.output_dir) / 'reports'
            self.file_manager.ensure_dir(final_dir)
            final_file = final_dir / f"{date}_report.json"
            
            # 加载已存在的结果
            existing_results = self._load_existing_results(final_file)
            existing_ids = {self._extract_paper_id_from_result(r) for r in existing_results}
        else:
            existing_ids = set()
        
        # 统计变量
        processed_count = 0
        success_count = 0
        fail_count = 0
        skip_count = 0

        # 顺序处理每篇论文
        for i, paper in enumerate(papers):
            # 检查是否已经处理过
            if date and paper.id in existing_ids:
                skip_count += 1
                if not silent:
                    self.console.print_skip(f"已处理的论文: {paper.id}")
                continue

            processed_count += 1

            if not silent:
                # 显示当前处理的论文信息
                self.console.print_info(f"🔍 处理第 {i+1}/{len(papers)} 项: {paper.translation}")

                # 显示整体进度条
                progress_bar = self._create_progress_bar(i, len(papers))
                remaining_papers = len(papers) - i - 1
                estimated_remaining = remaining_papers * 5  # 调整为5秒预估（简化提示词后应该更快）
                print(f"📊 进度: {progress_bar} {i}/{len(papers)} (成功:{success_count}, 失败:{fail_count}, 跳过:{skip_count}) 预计剩余: {estimated_remaining}秒")
            
            self.logger.info(f"开始分析论文: {paper.id} - {paper.title}")
            
            try:
                # 分析单篇论文（保持与批量分析相同的静默状态）
                result = self.analyze_single(paper, silent=silent)
                
                if result:
                    # 立即保存结果（如果提供了文件路径）
                    if final_file:
                        self._save_single_result(result, final_file)

                    results.append(result)
                    success_count += 1

                    if progress:
                        progress.update(True, f"{paper.id}")

                    if not silent:
                        self.console.print_success(f"✅ 完成: {paper.id} ({i+1}/{len(papers)})")

                    # 只记录日志，不重复显示
                    self.logger.info(f"论文分析完成: {paper.id}")
                else:
                    fail_count += 1

                    if progress:
                        progress.update(False, f"{paper.id}")

                    if not silent:
                        self.console.print_error(f"❌ 失败: {paper.id} ({i+1}/{len(papers)})")

                    self.logger.error(f"论文分析失败: {paper.id}")
                    
            except Exception as e:
                fail_count += 1

                if progress:
                    progress.update(False, f"{paper.id} - {e}")

                if not silent:
                    self.console.print_error(f"❌ 异常: {paper.id} - {e}")

                self.logger.error(f"论文分析异常: {paper.id} - {e}")
        
        # 显示最终统计
        if progress:
            progress.finish()
        
        if not silent:
            # 计算实际处理的论文数（排除跳过的）
            actually_processed = processed_count

            self.console.print_summary("分析完成统计", {
                "总论文数": len(papers),
                "跳过论文": skip_count,
                "实际处理": actually_processed,
                "成功分析": success_count,
                "分析失败": fail_count,
                "成功率": f"{success_count/max(actually_processed, 1)*100:.1f}%" if actually_processed > 0 else "0.0%"
            })

        self.logger.info(f"批量分析完成，成功: {success_count}/{actually_processed}，跳过: {skip_count}")
        return results
    
    def analyze_single(self, paper: Paper, silent: bool = False) -> Optional[AnalysisResult]:
        """
        分析单篇论文
        
        Args:
            paper: 论文对象
            silent: 是否静默模式
            
        Returns:
            分析结果，失败返回None
        """
        if not self.use_ai or not self.ai_client:
            if not silent:
                self.console.print_warning("AI分析未启用，返回基础结果")
            
            # 返回基础结果 - 使用新的数据结构
            # 对于基础结果，如果没有AI翻译，使用英文原文
            summary_zh = paper.summary[:200] + "..." if len(paper.summary) > 200 else paper.summary
            if not summary_zh or summary_zh == "暂无":
                summary_zh = "无摘要信息"
            
            return AnalysisResult(
                id=paper.id,
                title_en=paper.title,
                title_zh=paper.translation,  # 这里使用清洗时的translation字段
                url=paper.url,
                authors=paper.authors,
                publish_date=self._format_publish_date(paper.publish_date),
                summary_en=paper.summary,
                summary_zh=summary_zh,
                github_repo=paper.github_repo,
                project_page=paper.project_page,
                model_function="暂无"
            )
        
        # 添加重试机制
        max_retries = 3
        retry_delay = 2

        for attempt in range(max_retries):
            try:
                if not silent and attempt > 0:
                    self.console.print_info(f"重试第 {attempt} 次...")

                # 构建分析提示词
                prompt = self._build_analysis_prompt(paper)

                messages = [
                    {
                        "role": "user",
                        "content": [{
                            "type": "text",
                            "text": prompt
                        }]
                    }
                ]

                # 调用AI进行分析（带进度显示）
                import time
                import threading

                if not silent:
                    # 创建进度显示线程
                    progress_stop = threading.Event()
                    progress_thread = threading.Thread(
                        target=self._show_analysis_progress,
                        args=(progress_stop, f"分析论文: {paper.translation[:30]}...")
                    )
                    progress_thread.daemon = True
                    progress_thread.start()

                start_time = time.time()

                try:
                    # 使用线程超时处理（Windows兼容）
                    import concurrent.futures

                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(self.ai_client.chat, messages)
                        try:
                            response = future.result(timeout=90)  # 90秒超时
                        except concurrent.futures.TimeoutError:
                            if not silent:
                                progress_stop.set()
                                progress_thread.join(timeout=1)
                                print()  # 换行
                            raise TimeoutError(f"AI调用超时（90秒）")

                except TimeoutError:
                    raise  # 重新抛出超时异常
                finally:
                    if not silent:
                        progress_stop.set()
                        progress_thread.join(timeout=1)
                        print()  # 换行

                end_time = time.time()
                if not silent:
                    self.console.print_info(f"AI响应耗时: {end_time - start_time:.2f}秒")

                # 如果成功获得响应，跳出重试循环
                if response:
                    break
                else:
                    if attempt < max_retries - 1:
                        if not silent:
                            self.console.print_warning(f"AI响应为空，{retry_delay}秒后重试...")
                        time.sleep(retry_delay)
                        continue
                    else:
                        self.logger.error(f"AI分析失败，所有重试都返回空响应: {paper.id}")
                        return None

            except Exception as e:
                if attempt < max_retries - 1:
                    if not silent:
                        self.console.print_warning(f"AI调用异常: {e}，{retry_delay}秒后重试...")
                    self.logger.warning(f"AI调用异常，重试 {attempt + 1}/{max_retries}: {e}")
                    time.sleep(retry_delay)
                    continue
                else:
                    self.logger.error(f"AI分析失败，所有重试都异常: {paper.id} - {e}")
                    return None

        # 处理AI响应
        try:
            # 解析AI响应
            parsed_fields = self._parse_ai_response(response)

            # 格式化发表日期为YYYY-MM-DD格式
            publish_date = self._format_publish_date(paper.publish_date)

            # 处理翻译字段，确保不为空
            title_zh = parsed_fields.get('title_zh', '').strip()
            if not title_zh:
                title_zh = paper.title  # 如果AI没有提供翻译，使用英文原文
                self.logger.warning(f"使用英文标题作为中文翻译: {paper.id}")
            
            summary_zh = parsed_fields.get('summary_zh', '').strip()
            if not summary_zh:
                # 如果AI没有提供摘要翻译，使用英文摘要（截取前200字符）
                summary_zh = paper.summary[:200] + "..." if len(paper.summary) > 200 else paper.summary
                if not summary_zh or summary_zh == "暂无":
                    summary_zh = "无摘要信息"
                self.logger.warning(f"使用英文摘要作为中文翻译: {paper.id}")

            # 创建分析结果 - 使用新的数据结构
            result = AnalysisResult(
                id=paper.id,
                title_en=paper.title,
                title_zh=title_zh,
                url=paper.url,
                authors=paper.authors,
                publish_date=publish_date,
                summary_en=paper.summary,
                summary_zh=summary_zh,
                github_repo=paper.github_repo,
                project_page=paper.project_page,
                model_function=parsed_fields.get('model_function', '暂无')
            )

            return result

        except Exception as e:
            self.logger.error(f"解析AI响应异常: {paper.id} - {e}")
            return None
    
    def _build_analysis_prompt(self, paper: Paper) -> str:
        """
        构建AI分析提示词
        
        Args:
            paper: 论文对象
            
        Returns:
            提示词字符串
        """
        # 从paper对象中获取更多信息
        authors = getattr(paper, 'authors', '暂无')
        summary = getattr(paper, 'summary', '暂无')
        github_repo = getattr(paper, 'github_repo', '暂无')
        project_page = getattr(paper, 'project_page', '暂无')
        
        prompt = f"""你是一个AI论文翻译和分析专家。请基于提供的论文信息进行翻译和分析，严格按照指定格式输出结果。

## 输出格式要求：
**标题中文翻译**：[必须将英文标题翻译成准确的中文，保持技术术语的专业性]
**摘要中文翻译**：[必须将英文摘要翻译成中文，即使摘要很长也要完整翻译]
**模型功能**：[基于标题和摘要分析的主要功能和用途，50字以内]

## 重要注意事项：
- 必须严格按照上述格式输出，每行以对应标签开头
- 每个字段后面直接跟具体内容，不要使用方括号
- 标题中文翻译和摘要中文翻译是必填项，绝对不能写"暂无"或留空
- 翻译要准确专业，保持技术术语的准确性
- 模型功能要简洁明了，突出核心价值
- 如果摘要过长，请提取核心内容进行翻译，但不能省略

【待翻译和分析的论文信息】：
论文ID：{paper.id}
英文标题：{paper.title}
作者：{authors}
发表日期：{paper.publish_date}
英文摘要：{summary if summary != '暂无' else '无摘要信息'}
GitHub仓库：{github_repo}
项目页面：{project_page}

请务必完成标题和摘要的中文翻译，这是必须的任务。"""
        
        return prompt

    def _show_analysis_progress(self, stop_event, task_name):
        """
        显示AI分析进度动画

        Args:
            stop_event: 停止事件
            task_name: 任务名称
        """
        import sys
        import time

        spinner = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        start_time = time.time()
        i = 0
        warning_shown = False

        while not stop_event.is_set():
            elapsed = int(time.time() - start_time)
            minutes, seconds = divmod(elapsed, 60)
            time_str = f"{minutes:02d}:{seconds:02d}"

            # 在75秒时显示警告
            if elapsed >= 75 and not warning_shown:
                sys.stdout.write(f'\r🧠 {task_name} {spinner[i % len(spinner)]} 已耗时: {time_str} ⚠️ 响应较慢...')
                warning_shown = True
            else:
                sys.stdout.write(f'\r🧠 {task_name} {spinner[i % len(spinner)]} 已耗时: {time_str}')

            sys.stdout.flush()

            time.sleep(0.1)
            i += 1

    def _create_progress_bar(self, current, total, width=50):
        """
        创建进度条

        Args:
            current: 当前进度
            total: 总数
            width: 进度条宽度

        Returns:
            进度条字符串
        """
        if total == 0:
            return "[" + "░" * width + "]"

        progress = current / total
        filled = int(width * progress)
        bar = "█" * filled + "░" * (width - filled)
        return f"[{bar}]"
    
    def _parse_ai_response(self, response: str) -> Dict[str, str]:
        """
        解析AI响应，提取翻译和分析结果
        
        Args:
            response: AI响应文本
            
        Returns:
            解析后的字段字典
        """
        parsed_fields = {
            'title_zh': '',
            'summary_zh': '',
            'model_function': '暂无'
        }
        
        try:
            lines = response.strip().split('\n')
            
            for line in lines:
                line = line.strip()
                if line.startswith('**标题中文翻译**：'):
                    parsed_fields['title_zh'] = line.replace('**标题中文翻译**：', '').strip()
                elif line.startswith('**摘要中文翻译**：'):
                    parsed_fields['summary_zh'] = line.replace('**摘要中文翻译**：', '').strip()
                elif line.startswith('**模型功能**：'):
                    parsed_fields['model_function'] = line.replace('**模型功能**：', '').strip()
            
            # 特殊处理：title_zh 和 summary_zh 不能为空，如果为空则使用英文原文
            if not parsed_fields['title_zh'] or parsed_fields['title_zh'].strip() == '':
                self.logger.warning("AI未提供标题翻译，使用英文原文")
                # 这里会在调用处使用英文标题作为备选
            
            if not parsed_fields['summary_zh'] or parsed_fields['summary_zh'].strip() == '':
                self.logger.warning("AI未提供摘要翻译，使用英文原文")
                # 这里会在调用处使用英文摘要作为备选
            
            # model_function 可以为暂无
            if not parsed_fields['model_function'] or parsed_fields['model_function'].strip() == '':
                parsed_fields['model_function'] = '暂无'
                    
        except Exception as e:
            self.logger.warning(f"解析AI响应失败: {e}")
        
        return parsed_fields
    
    def _format_publish_date(self, date_str: str) -> str:
        """
        格式化发表日期为YYYY-MM-DD格式
        
        Args:
            date_str: 原始日期字符串
            
        Returns:
            格式化后的日期字符串
        """
        if not date_str or date_str == '暂无':
            return '暂无'
        
        try:
            # 处理ISO格式日期 (2025-07-31T17:00:30.000Z)
            if 'T' in date_str:
                date_part = date_str.split('T')[0]
                return date_part
            
            # 如果已经是YYYY-MM-DD格式
            if len(date_str) == 10 and date_str.count('-') == 2:
                return date_str
            
            # 其他格式尝试解析
            import re
            from datetime import datetime
            
            # 尝试匹配YYYY-MM-DD格式
            match = re.search(r'(\d{4}-\d{2}-\d{2})', date_str)
            if match:
                return match.group(1)
            
            # 如果无法解析，返回原始字符串
            return date_str
            
        except Exception as e:
            self.logger.warning(f"日期格式化失败: {e}")
            return date_str
    
    def _load_existing_results(self, file_path: Path) -> List[Dict[str, Any]]:
        """
        加载已存在的结果文件
        
        Args:
            file_path: 文件路径
            
        Returns:
            已存在的结果列表
        """
        if file_path.exists():
            try:
                data = self.file_manager.load_json(file_path)
                return data if isinstance(data, list) else []
            except Exception as e:
                self.logger.error(f"加载已存在结果失败: {e}")
                return []
        return []
    
    def _save_single_result(self, result: AnalysisResult, file_path: Path):
        """
        保存单个分析结果到文件
        
        Args:
            result: 分析结果
            file_path: 文件路径
        """
        try:
            # 加载现有结果
            existing_results = self._load_existing_results(file_path)
            
            # 移除已存在的相同ID论文
            existing_results = [
                r for r in existing_results 
                if self._extract_paper_id_from_result(r) != result.paper_id
            ]
            
            # 添加新结果
            existing_results.append(result.to_dict())
            
            # 保存到文件
            self.file_manager.save_json(existing_results, file_path)
            
        except Exception as e:
            self.logger.error(f"保存单个结果失败: {e}")
    
    def _extract_paper_id_from_result(self, result: Dict[str, Any]) -> str:
        """
        从结果中提取论文ID
        
        Args:
            result: 结果字典
            
        Returns:
            论文ID
        """
        # 尝试多种可能的字段名
        for field in ['paper_id', 'id']:
            if field in result:
                return result[field]
        
        # 从URL中提取
        url = result.get('paper_url', '')
        if url:
            return url.split('/')[-1]
        
        return ''
    
    def create_daily_report(self, date: str, analysis_results: List[AnalysisResult]) -> DailyReport:
        """
        创建日报
        
        Args:
            date: 日期字符串
            analysis_results: 分析结果列表
            
        Returns:
            日报对象
        """
        report = DailyReport(
            date=date,
            total_papers=len(analysis_results),
            analysis_results=analysis_results
        )
        
        return report
    
    def save_daily_report(self, report: DailyReport) -> bool:
        """
        保存日报到文件
        
        Args:
            report: 日报对象
            
        Returns:
            是否成功
        """
        try:
            # 确保报告目录存在
            reports_dir = Path(self.output_dir) / 'reports'
            self.file_manager.ensure_dir(reports_dir)
            
            # 构建文件路径
            file_path = reports_dir / f"{report.date}_report.json"
            
            # 保存报告
            success = report.save_to_file(str(file_path))
            
            if success:
                self.logger.info(f"日报保存成功: {file_path}")
            else:
                self.logger.error(f"日报保存失败: {file_path}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"保存日报异常: {e}")
            return False
    
    def get_analysis_statistics(self) -> Dict[str, Any]:
        """
        获取分析统计信息
        
        Returns:
            统计信息字典
        """
        reports_dir = Path(self.output_dir) / 'reports'
        
        if not reports_dir.exists():
            return {"total_reports": 0, "reports": []}
        
        json_files = list(reports_dir.glob("*_report.json"))
        
        return {
            "total_reports": len(json_files),
            "reports": [f.stem for f in json_files],
            "reports_dir": str(reports_dir)
        }


# 便捷函数
def create_analyzer(config: Dict[str, Any]) -> PaperAnalyzer:
    """
    便捷函数：创建分析器实例
    
    Args:
        config: 配置字典
        
    Returns:
        PaperAnalyzer实例
    """
    return PaperAnalyzer(config)

def analyze_papers(papers: List[Paper], date: str = None,
                  output_dir: str = 'data/daily_reports',
                  ai_model: str = 'zhipu', silent: bool = False) -> List[AnalysisResult]:
    """
    便捷函数：分析论文
    
    Args:
        papers: 论文列表
        date: 日期字符串
        output_dir: 输出目录
        ai_model: AI模型类型
        silent: 是否静默模式
        
    Returns:
        分析结果列表
    """
    config = {
        'output_dir': output_dir,
        'ai_model': ai_model
    }
    analyzer = PaperAnalyzer(config)
    return analyzer.analyze_batch(papers, date, silent)
