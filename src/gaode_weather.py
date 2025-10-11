# 高德天气 API 客户端
# 支持智能缓存，1小时内最多请求一次API

import requests
import time
import logging
from typing import Optional, Dict, Any


class GaodeWeather:
    """
    高德天气API客户端
    
    特性:
    - 智能缓存：1小时内只请求一次API
    - 错误处理：网络错误和API错误处理
    - 数据验证：响应数据有效性检查
    - 日志记录：详细的操作日志
    """
    
    # 缓存时间：1小时 = 3600秒
    CACHE_DURATION = 3600
    
    def __init__(self, api_key: str, city: str, timeout: int = 10):
        """
        初始化天气API客户端
        
        Args:
            api_key: 高德地图API密钥
            city: 城市名称或adcode
            timeout: 请求超时时间（秒）
        """
        self.api_key = api_key
        self.city = city
        self.timeout = timeout
        
        # 缓存相关
        self._cache_data: Optional[Dict[str, Any]] = None
        self._cache_timestamp: float = 0
        
        # 日志
        self.logger = logging.getLogger(__name__)
        
        # API基础URL
        self._base_url = "https://restapi.amap.com/v3/weather/weatherInfo"
        
        self.logger.info(f"高德天气API客户端初始化完成: 城市={city}")
    
    def _is_cache_valid(self) -> bool:
        """检查缓存是否有效"""
        if self._cache_data is None:
            return False
        
        elapsed = time.time() - self._cache_timestamp
        is_valid = elapsed < self.CACHE_DURATION
        
        if not is_valid:
            self.logger.debug(f"缓存已过期: 已过去 {elapsed:.1f} 秒")
        
        return is_valid
    
    def _fetch_weather_data(self) -> Dict[str, Any]:
        """从API获取天气数据"""
        params = {
            'key': self.api_key,
            'city': self.city,
            'extensions': 'base'  # 获取实况天气
        }
        
        try:
            self.logger.debug(f"请求高德天气API: 城市={self.city}")
            
            response = requests.get(
                self._base_url, 
                params=params, 
                timeout=self.timeout
            )
            response.raise_for_status()  # 抛出HTTP错误
            
            data = response.json()
            
            # 检查API响应状态
            if data.get('status') != '1':
                error_msg = data.get('info', '未知错误')
                raise ValueError(f"高德API错误: {error_msg}")
            
            # 检查数据完整性
            lives = data.get('lives', [])
            if not lives:
                raise ValueError("API返回数据为空")
            
            # 更新缓存
            self._cache_data = data
            self._cache_timestamp = time.time()
            
            self.logger.info(f"天气数据获取成功: 城市={self.city}")
            return data
            
        except requests.exceptions.Timeout:
            self.logger.error(f"API请求超时: {self.timeout}秒")
            raise TimeoutError("天气API请求超时")
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"网络请求失败: {e}")
            raise ConnectionError(f"网络请求失败: {e}")
            
        except ValueError as e:
            self.logger.error(f"API数据错误: {e}")
            raise
            
        except Exception as e:
            self.logger.error(f"获取天气数据时发生未知错误: {e}")
            raise RuntimeError(f"获取天气数据失败: {e}")
    
    def _get_weather_data(self) -> Dict[str, Any]:
        """获取天气数据（带缓存）"""
        if self._is_cache_valid():
            self.logger.debug("使用缓存的天气数据")
            return self._cache_data
        
        return self._fetch_weather_data()
    
    def get_current_weather(self) -> Dict[str, Any]:
        """
        获取当前天气完整信息
        
        Returns:
            包含所有天气信息的字典
        """
        data = self._get_weather_data()
        return data['lives'][0]
    
    def get_temperature(self) -> str:
        """获取温度"""
        weather_info = self.get_current_weather()
        return weather_info['temperature']
    
    def get_weather_type(self) -> str:
        """获取天气现象（如：晴、多云、雨等）"""
        weather_info = self.get_current_weather()
        return weather_info['weather']
    
    def get_wind_direction(self) -> str:
        """获取风向"""
        weather_info = self.get_current_weather()
        return weather_info['winddirection']
    
    def get_wind_power(self) -> str:
        """获取风力等级"""
        weather_info = self.get_current_weather()
        return weather_info['windpower']
    
    def get_humidity(self) -> str:
        """获取相对湿度"""
        weather_info = self.get_current_weather()
        return weather_info['humidity']
    
    def get_cache_info(self) -> Dict[str, Any]:
        """
        获取缓存信息
        
        Returns:
            缓存状态信息
        """
        if self._cache_data is None:
            return {
                'has_cache': False,
                'cache_age': 0,
                'cache_valid': False
            }
        
        cache_age = time.time() - self._cache_timestamp
        
        return {
            'has_cache': True,
            'cache_age': cache_age,
            'cache_valid': self._is_cache_valid(),
            'cache_expires_in': max(0, self.CACHE_DURATION - cache_age)
        }
    
    def clear_cache(self) -> None:
        """清除缓存"""
        self._cache_data = None
        self._cache_timestamp = 0
        self.logger.info("天气数据缓存已清除")
    
    def __str__(self) -> str:
        """字符串表示"""
        cache_info = self.get_cache_info()
        return f"GaodeWeather(city={self.city}, cache_valid={cache_info['cache_valid']})"


# 简化的使用示例
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    API_KEY = "your_api_key_here"
    CITY = "310000"  # 上海的adcode
    
    if API_KEY != "your_api_key_here":
        try:
            weather = GaodeWeather(api_key=API_KEY, city=CITY)
            
            print(f"🌡️ 温度: {weather.get_temperature()}°C")
            print(f"☁️ 天气: {weather.get_weather_type()}")
            print(f"💧 湿度: {weather.get_humidity()}%")
            print(f"🌬️ 风向: {weather.get_wind_direction()}")
            print(f"💨 风力: {weather.get_wind_power()}级")
            
            # 缓存信息
            cache_info = weather.get_cache_info()
            print(f"\n📊 缓存状态: {cache_info['cache_valid']}")
            
        except Exception as e:
            print(f"❌ 错误: {e}")
    else:
        print("⚠️ 请设置有效的API密钥")
