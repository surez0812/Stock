import os
import logging
import uuid
import oss2
from datetime import datetime
import requests

class OSSClient:
    """阿里云OSS客户端，用于上传文件到阿里云OSS存储"""
    
    def __init__(self):
        """初始化OSS客户端"""
        # 配置日志
        logging.basicConfig(level=logging.INFO)
        
        # 从环境变量获取OSS配置
        self.access_key_id = os.getenv("ALIYUN_ACCESS_KEY_ID")
        self.access_key_secret = os.getenv("ALIYUN_ACCESS_KEY_SECRET")
        self.bucket_name = os.getenv("ALIYUN_OSS_BUCKET") or "surezhang-image-analysis"
        self.endpoint = os.getenv("ALIYUN_OSS_ENDPOINT") or "oss-cn-beijing.aliyuncs.com"
        
        # 详细记录配置信息
        logging.info(f"OSS初始化配置: endpoint={self.endpoint}, bucket={self.bucket_name}")
        logging.info(f"OSS访问密钥ID: {self.access_key_id[:4]}{'*' * 8}{self.access_key_id[-4:] if self.access_key_id and len(self.access_key_id) > 8 else ''}")
        
        # 初始化OSS客户端
        self.initialized = False
        self.auth = None
        self.bucket = None
        
        # 如果有访问密钥，则初始化客户端
        if self.access_key_id and self.access_key_secret:
            try:
                logging.info("正在初始化阿里云OSS客户端...")
                logging.info(f"使用endpoint: {self.endpoint}")
                self.auth = oss2.Auth(self.access_key_id, self.access_key_secret)
                self.bucket = oss2.Bucket(self.auth, self.endpoint, self.bucket_name)
                
                # 测试OSS连接
                try:
                    logging.info("正在测试OSS连接...")
                    # 列出Bucket中的文件（最多10个）以验证连接
                    objects = list(self.bucket.list_objects().object_list)
                    object_count = len(objects)
                    logging.info(f"OSS连接测试成功，Bucket中有{object_count}个对象")
                    if object_count > 0:
                        logging.info(f"Bucket中的部分对象: {[obj.key for obj in objects[:3]]}")
                    
                    # 验证Bucket配置
                    try:
                        # 获取存储桶配置
                        bucket_info = self.bucket.get_bucket_info()
                        logging.info(f"Bucket创建时间: {bucket_info.creation_date}")
                        logging.info(f"Bucket位置: {bucket_info.location}")
                        logging.info(f"Bucket存储类型: {bucket_info.storage_class}")
                        
                        # 获取存储桶ACL
                        acl = self.bucket.get_bucket_acl()
                        logging.info(f"Bucket ACL: {acl.acl}")
                        if acl.acl != oss2.BUCKET_ACL_PUBLIC_READ and acl.acl != oss2.BUCKET_ACL_PUBLIC_READ_WRITE:
                            logging.warning(f"警告：Bucket没有设置公共读取权限，这可能导致AI服务无法访问图片")
                    except Exception as e:
                        logging.warning(f"获取Bucket信息失败: {str(e)}")
                    
                    self.initialized = True
                    logging.info("成功初始化阿里云OSS客户端")
                except oss2.exceptions.ServerError as e:
                    logging.error(f"OSS服务器错误: {str(e)}")
                    if hasattr(e, 'status'):
                        logging.error(f"HTTP状态码: {e.status}")
                    if hasattr(e, 'request_id'):
                        logging.error(f"请求ID: {e.request_id}")
                    if hasattr(e, 'message'):
                        logging.error(f"错误消息: {e.message}")
                except oss2.exceptions.ClientError as e:
                    logging.error(f"OSS客户端错误: {str(e)}")
                    logging.error(f"错误代码: {e.code}, 错误消息: {e.message}")
                except Exception as e:
                    logging.error(f"测试OSS连接失败: {str(e)}")
            except Exception as e:
                logging.error(f"初始化阿里云OSS客户端失败: {str(e)}")
                logging.error(f"异常类型: {type(e).__name__}")
                if hasattr(e, 'code'):
                    logging.error(f"错误代码: {e.code}")
                if hasattr(e, 'message'):
                    logging.error(f"错误消息: {e.message}")
        else:
            logging.warning("未配置阿里云OSS访问密钥，OSS上传功能将不可用")
            if not self.access_key_id:
                logging.warning("缺少ALIYUN_ACCESS_KEY_ID环境变量")
            if not self.access_key_secret:
                logging.warning("缺少ALIYUN_ACCESS_KEY_SECRET环境变量")
    
    def is_available(self):
        """检查OSS客户端是否可用"""
        return self.initialized
    
    def test_url_accessibility(self, url, timeout=5):
        """测试URL是否可以被公开访问"""
        try:
            logging.info(f"测试URL可访问性: {url}")
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            response = requests.head(url, headers=headers, timeout=timeout)
            
            if response.status_code == 200:
                logging.info(f"URL测试成功，状态码: {response.status_code}")
                content_type = response.headers.get('Content-Type', '')
                content_length = response.headers.get('Content-Length', 'unknown')
                logging.info(f"Content-Type: {content_type}, Content-Length: {content_length}")
                return True, None
            else:
                error_msg = f"URL测试失败，状态码: {response.status_code}"
                logging.warning(error_msg)
                return False, error_msg
        except Exception as e:
            error_msg = f"测试URL时出错: {str(e)}"
            logging.warning(error_msg)
            return False, error_msg
    
    def upload_file(self, file_path, content_type='image/jpeg'):
        """
        上传文件到OSS
        
        Args:
            file_path: 本地文件路径
            content_type: 文件内容类型
            
        Returns:
            (success, url): 上传是否成功，如果成功则包含可访问的URL
        """
        if not self.initialized:
            logging.error("OSS客户端未初始化，无法上传文件")
            return False, None
            
        if not os.path.exists(file_path):
            logging.error(f"要上传的文件不存在: {file_path}")
            return False, None
            
        try:
            # 生成OSS对象名称
            file_name = os.path.basename(file_path)
            date_prefix = datetime.now().strftime('%Y%m%d')
            object_name = f"stock-images/{date_prefix}/{uuid.uuid4().hex}_{file_name}"
            
            # 获取文件信息
            file_size = os.path.getsize(file_path)
            logging.info(f"准备上传文件到OSS: {file_path} -> {self.bucket_name}/{object_name}，文件大小: {file_size} 字节")
            
            # 如果文件大于5MB，显示上传进度
            progress_callback = None
            if file_size > 5 * 1024 * 1024:  # 5MB
                def percentage(consumed_bytes, total_bytes):
                    if total_bytes:
                        rate = int(100 * (float(consumed_bytes) / float(total_bytes)))
                        logging.info(f'上传进度: {rate}%')
                progress_callback = percentage
            
            # 上传时设置Content-Type和ACL
            headers = {
                'Content-Type': content_type,
                'x-oss-object-acl': 'public-read'  # 设置为公共可读
            }
            
            logging.info(f"开始上传文件到OSS，对象名: {object_name}")
            logging.info(f"使用Content-Type: {content_type}")
            
            # 执行上传
            try:
                logging.info("正在执行上传操作...")
                if progress_callback:
                    self.bucket.put_object_from_file(
                        object_name, file_path, 
                        headers=headers,
                        progress_callback=progress_callback
                    )
                else:
                    self.bucket.put_object_from_file(object_name, file_path, headers=headers)
                
                logging.info(f"上传操作完成")
                
                # 获取可访问的URL
                url = f"https://{self.bucket_name}.{self.endpoint}/{object_name}"
                logging.info(f"文件上传成功，URL: {url}")
                
                # 验证文件是否设置了正确的ACL
                try:
                    object_acl = self.bucket.get_object_acl(object_name).acl
                    logging.info(f"对象ACL: {object_acl}")
                    if object_acl != oss2.OBJECT_ACL_PUBLIC_READ:
                        logging.warning("警告：对象没有设置为公共读取权限")
                        # 尝试重新设置ACL
                        try:
                            self.bucket.put_object_acl(object_name, oss2.OBJECT_ACL_PUBLIC_READ)
                            logging.info("已重新设置对象为公共读取权限")
                        except Exception as acl_e:
                            logging.error(f"设置对象ACL失败: {str(acl_e)}")
                except Exception as e:
                    logging.warning(f"获取对象ACL失败: {str(e)}")
                
                # 验证是否可以访问此URL
                is_accessible, error = self.test_url_accessibility(url)
                if not is_accessible:
                    logging.warning(f"OSS URL可能无法被阿里云AI服务访问: {error}")
                    logging.info("尝试修复URL访问问题...")
                    
                    # 生成带有时间戳的签名URL，有效期为1小时
                    try:
                        signed_url = self.bucket.sign_url('GET', object_name, 3600)
                        logging.info(f"生成带签名的临时URL: {signed_url}")
                        # 测试签名URL
                        is_signed_accessible, error = self.test_url_accessibility(signed_url)
                        if is_signed_accessible:
                            logging.info("签名URL可以访问，将使用这个URL")
                            return True, signed_url
                        else:
                            logging.warning(f"签名URL也无法访问: {error}")
                    except Exception as e:
                        logging.error(f"生成签名URL失败: {str(e)}")
                
                return True, url
                
            except oss2.exceptions.ServerError as e:
                logging.error(f"OSS服务器错误: {str(e)}")
                if hasattr(e, 'status'):
                    logging.error(f"HTTP状态码: {e.status}")
                if hasattr(e, 'request_id'):
                    logging.error(f"请求ID: {e.request_id}")
                if hasattr(e, 'message'):
                    logging.error(f"错误消息: {e.message}")
                if hasattr(e, 'details'):
                    logging.error(f"详细信息: {e.details}")
                return False, None
                
            except oss2.exceptions.ClientError as e:
                logging.error(f"OSS客户端错误: {str(e)}")
                logging.error(f"错误代码: {e.code}, 错误消息: {e.message}")
                return False, None
        except Exception as e:
            error_msg = f"上传文件到OSS失败: {str(e)}"
            logging.error(error_msg)
            logging.error(f"异常类型: {type(e).__name__}")
            # 记录请求ID，有助于阿里云排查问题
            if hasattr(e, 'request_id'):
                logging.error(f"请求ID: {e.request_id}")
            return False, None
            
# 创建OSS客户端实例
oss_client = OSSClient() 