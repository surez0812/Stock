"""
技术指标计算模块 - 使用 TA-Lib 计算各种技术指标
"""
import talib
import numpy as np
import pandas as pd

class TechnicalIndicators:
    """技术指标计算类"""
    
    @staticmethod
    def calculate_macd(close_prices, fastperiod=12, slowperiod=26, signalperiod=9):
        """计算MACD指标
        
        Args:
            close_prices: 收盘价序列
            fastperiod: 快线周期
            slowperiod: 慢线周期
            signalperiod: 信号线周期
            
        Returns:
            包含MACD指标的DataFrame
        """
        try:
            macd, signal, hist = talib.MACD(
                close_prices,
                fastperiod=fastperiod,
                slowperiod=slowperiod,
                signalperiod=signalperiod
            )
            return pd.DataFrame({
                'MACD': macd,
                'Signal': signal,
                'Histogram': hist
            })
        except Exception as e:
            print(f"计算MACD出错: {e}")
            return None
    
    @staticmethod
    def calculate_rsi(close_prices, period=14):
        """计算RSI指标
        
        Args:
            close_prices: 收盘价序列
            period: RSI周期
            
        Returns:
            RSI值序列
        """
        try:
            rsi = talib.RSI(close_prices, timeperiod=period)
            return pd.Series(rsi, name='RSI')
        except Exception as e:
            print(f"计算RSI出错: {e}")
            return None
    
    @staticmethod
    def calculate_bollinger_bands(close_prices, period=20, nbdevup=2, nbdevdn=2):
        """计算布林带
        
        Args:
            close_prices: 收盘价序列
            period: 移动平均周期
            nbdevup: 上轨标准差倍数
            nbdevdn: 下轨标准差倍数
            
        Returns:
            包含布林带上中下轨的DataFrame
        """
        try:
            upper, middle, lower = talib.BBANDS(
                close_prices,
                timeperiod=period,
                nbdevup=nbdevup,
                nbdevdn=nbdevdn
            )
            return pd.DataFrame({
                'BB_Upper': upper,
                'BB_Middle': middle,
                'BB_Lower': lower
            })
        except Exception as e:
            print(f"计算布林带出错: {e}")
            return None
    
    @staticmethod
    def calculate_ma(close_prices, periods=[5, 10, 20, 30, 60]):
        """计算多个周期的移动平均线
        
        Args:
            close_prices: 收盘价序列
            periods: 移动平均周期列表
            
        Returns:
            包含多个周期MA的DataFrame
        """
        try:
            ma_dict = {}
            for period in periods:
                ma = talib.MA(close_prices, timeperiod=period)
                ma_dict[f'MA{period}'] = ma
            return pd.DataFrame(ma_dict)
        except Exception as e:
            print(f"计算移动平均线出错: {e}")
            return None
    
    @staticmethod
    def calculate_kdj(high_prices, low_prices, close_prices, fastk_period=9, slowk_period=3, slowd_period=3):
        """计算KDJ指标
        
        Args:
            high_prices: 最高价序列
            low_prices: 最低价序列
            close_prices: 收盘价序列
            fastk_period: 快速%K周期
            slowk_period: 慢速%K周期
            slowd_period: 慢速%D周期
            
        Returns:
            包含KDJ指标的DataFrame
        """
        try:
            k, d = talib.STOCH(
                high_prices,
                low_prices,
                close_prices,
                fastk_period=fastk_period,
                slowk_period=slowk_period,
                slowk_matype=0,
                slowd_period=slowd_period,
                slowd_matype=0
            )
            
            # 计算J值
            j = 3 * k - 2 * d
            
            return pd.DataFrame({
                'K': k,
                'D': d,
                'J': j
            })
        except Exception as e:
            print(f"计算KDJ出错: {e}")
            return None
    
    @staticmethod
    def calculate_all_indicators(df):
        """计算所有技术指标
        
        Args:
            df: 包含OHLCV数据的DataFrame
            
        Returns:
            包含所有技术指标的DataFrame
        """
        try:
            result = pd.DataFrame(index=df.index)
            
            # 计算MACD
            macd_df = TechnicalIndicators.calculate_macd(df['Close'])
            if macd_df is not None:
                result = pd.concat([result, macd_df], axis=1)
            
            # 计算RSI
            rsi = TechnicalIndicators.calculate_rsi(df['Close'])
            if rsi is not None:
                result['RSI'] = rsi
            
            # 计算布林带
            bb_df = TechnicalIndicators.calculate_bollinger_bands(df['Close'])
            if bb_df is not None:
                result = pd.concat([result, bb_df], axis=1)
            
            # 计算移动平均线
            ma_df = TechnicalIndicators.calculate_ma(df['Close'])
            if ma_df is not None:
                result = pd.concat([result, ma_df], axis=1)
            
            # 计算KDJ
            kdj_df = TechnicalIndicators.calculate_kdj(df['High'], df['Low'], df['Close'])
            if kdj_df is not None:
                result = pd.concat([result, kdj_df], axis=1)
            
            return result
        except Exception as e:
            print(f"计算技术指标出错: {e}")
            return None 