"""
AKShare客户端 - 提供股票数据获取和K线图生成功能
"""
import os
import datetime
import pandas as pd
import akshare as ak
import mplfinance as mpf
import matplotlib
matplotlib.use('Agg')  # 使用非交互式后端，避免需要图形界面

class AKShareClient:
    """AKShare数据获取和处理客户端"""
    
    def __init__(self, image_save_path='app/static/images/charts'):
        """初始化客户端
        
        Args:
            image_save_path: K线图保存路径
        """
        self.image_save_path = image_save_path
        # 确保保存路径存在
        os.makedirs(image_save_path, exist_ok=True)
    
    def get_stock_data(self, symbol, period='daily', start_date=None, end_date=None, adjust='qfq'):
        """获取股票数据
        
        Args:
            symbol: 股票代码，如"sh000001"(上证指数)，"sz000001"(平安银行)
            period: 周期，可选 'daily'(日线), 'weekly'(周线), 'monthly'(月线)
            start_date: 起始日期，格式"YYYY-MM-DD"，默认为90天前
            end_date: 结束日期，格式"YYYY-MM-DD"，默认为今天
            adjust: 复权方式，可选 'qfq'(前复权), 'hfq'(后复权), None(不复权)
            
        Returns:
            处理后的DataFrame
        """
        # 设置默认日期范围
        if end_date is None:
            end_date = datetime.datetime.now().strftime('%Y-%m-%d')
        if start_date is None:
            # 默认获取90天数据
            start_date = (datetime.datetime.now() - datetime.timedelta(days=90)).strftime('%Y-%m-%d')
        
        try:
            # 判断是指数还是个股
            if symbol.startswith('sh00') or symbol.startswith('sz39'):
                # 获取指数数据
                df = ak.stock_zh_index_daily(symbol=symbol)
            else:
                # 获取个股数据
                df = ak.stock_zh_a_daily(symbol=symbol, adjust=adjust)
            
            # 数据预处理
            df = self._preprocess_data(df)
            
            # 筛选日期范围
            df = df[(df.index >= start_date) & (df.index <= end_date)]
            
            return df
        
        except Exception as e:
            print(f"获取股票数据出错: {e}")
            return None
    
    def _preprocess_data(self, df):
        """预处理原始数据为mplfinance所需格式
        
        Args:
            df: 原始DataFrame
            
        Returns:
            处理后的DataFrame
        """
        # 提取关键字段并重命名列
        if 'date' in df.columns:  # 指数数据
            df = df[["date", "open", "high", "low", "close", "volume"]]
            df = df.rename(columns={
                "date": "Date", 
                "open": "Open", 
                "high": "High", 
                "low": "Low", 
                "close": "Close", 
                "volume": "Volume"
            })
        else:  # 个股数据
            df = df[["日期", "开盘", "最高", "最低", "收盘", "成交量"]]
            df = df.rename(columns={
                "日期": "Date", 
                "开盘": "Open", 
                "最高": "High", 
                "最低": "Low", 
                "收盘": "Close", 
                "成交量": "Volume"
            })
        
        # 转换日期格式并设为索引
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.set_index("Date").sort_index()
        
        # 确保数值类型正确
        df = df.apply(pd.to_numeric)
        
        return df
    
    def generate_kline_chart(self, df, title=None, days=60, show_volume=True, 
                            mav=(5, 20), style='binance', filename=None):
        """生成K线图
        
        Args:
            df: 股票数据DataFrame
            title: 图表标题
            days: 显示天数
            show_volume: 是否显示成交量
            mav: 移动平均线周期，如(5,20)表示5日、20日均线
            style: 图表样式
            filename: 保存的文件名，默认使用随机名称
            
        Returns:
            生成的图表文件路径
        """
        # 确保有足够的数据
        if df is None or len(df) == 0:
            return None
        
        # 只取最近N天的数据
        if len(df) > days:
            plot_data = df[-days:]
        else:
            plot_data = df
        
        # 设置文件名
        if filename is None:
            # 使用时间戳生成唯一文件名
            timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
            filename = f"kline_{timestamp}.png"
        
        file_path = os.path.join(self.image_save_path, filename)
        
        # 设置图表样式
        s = mpf.make_mpf_style(
            base_mpf_style=style,
            marketcolors=mpf.make_marketcolors(
                up='red',         # 上涨为红色 
                down='green',     # 下跌为绿色，符合中国股市习惯
                edge='inherit',
                wick='inherit',
                volume='inherit'
            )
        )
        
        # 生成K线图
        fig, axes = mpf.plot(
            plot_data,
            type='candle',
            title=title,
            ylabel='价格',
            ylabel_lower='成交量',
            volume=show_volume,
            mav=mav,
            style=s,
            figsize=(12, 8),
            returnfig=True
        )
        
        # 保存图表
        fig.savefig(file_path, dpi=100)
        
        return file_path
    
    def get_stock_list(self, market='A股'):
        """获取股票列表
        
        Args:
            market: 市场类型，默认为'A股'
            
        Returns:
            股票列表DataFrame
        """
        try:
            if market == 'A股':
                # 获取A股股票列表
                stock_list = ak.stock_zh_a_spot()
                # 提取代码和名称
                stock_list = stock_list[['代码', '名称']].rename(
                    columns={'代码': 'code', '名称': 'name'})
                return stock_list
            else:
                return None
        except Exception as e:
            print(f"获取股票列表出错: {e}")
            return None
    
    def get_index_list(self):
        """获取常用指数列表
        
        Returns:
            指数列表，包含代码和名称
        """
        # 常用指数列表
        indices = [
            {'code': 'sh000001', 'name': '上证指数'},
            {'code': 'sz399001', 'name': '深证成指'},
            {'code': 'sz399006', 'name': '创业板指'},
            {'code': 'sh000300', 'name': '沪深300'},
            {'code': 'sh000016', 'name': '上证50'},
            {'code': 'sh000905', 'name': '中证500'},
            {'code': 'sh000852', 'name': '中证1000'}
        ]
        return pd.DataFrame(indices)

# 测试代码
if __name__ == '__main__':
    client = AKShareClient()
    # 获取上证指数数据
    df = client.get_stock_data('sh000001')
    
    if df is not None:
        # 生成K线图
        file_path = client.generate_kline_chart(df, title='上证指数K线图')
        print(f"K线图已生成: {file_path}") 