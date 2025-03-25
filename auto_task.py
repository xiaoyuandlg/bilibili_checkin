import requests
import json
import time
import os
import sys
from datetime import datetime, timedelta, timezone
from loguru import logger
import random

# 配置日志
class BeijingFormatter:
    @staticmethod
    def format(record):
        dt = datetime.fromtimestamp(record["time"].timestamp(), tz=timezone.utc)
        local_dt = dt + timedelta(hours=8)
        record["extra"]["local_time"] = local_dt.strftime('%H:%M:%S,%f')[:-3]
        return "{time:YYYY-MM-DD HH:mm:ss,SSS}(CST {extra[local_time]}) - {level} - {message}\n"

logger.remove()
logger.add(sys.stdout, format=BeijingFormatter.format, level="INFO", colorize=True)

class BilibiliTask:
    def __init__(self, cookie):
        self.cookie = cookie
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/86.0.4240.198 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Cookie': cookie
        }
        
    def get_csrf(self):
        """从cookie获取csrf"""
        for item in self.cookie.split(';'):
            if item.strip().startswith('bili_jct'):
                return item.split('=')[1]
        return None

    def check_login_status(self):
        """检查登录状态"""
        try:
            res = requests.get('https://api.bilibili.com/x/web-interface/nav', headers=self.headers)
            if res.json()['code'] == -101:
                return False, '账号未登录'
            return True, None
        except Exception as e:
            return False, str(e)
        
    def share_video(self):
        """分享视频"""
        try:
            # 获取随机视频
            res = requests.get('https://api.bilibili.com/x/web-interface/dynamic/region?ps=1&rid=1', headers=self.headers)
            bvid = res.json()['data']['archives'][0]['bvid']
            
            # 分享视频
            data = {
                'bvid': bvid,
                'csrf': self.get_csrf()
            }
            res = requests.post('https://api.bilibili.com/x/web-interface/share/add', headers=self.headers, data=data)
            if res.json()['code'] == 0:
                return True, None
            else:
                return False, res.json().get('message', '未知错误')
        except Exception as e:
            return False, str(e)
            
    def watch_video(self, bvid):
        """观看视频"""
        try:
            data = {
                'bvid': bvid,
                'csrf': self.get_csrf(),
                'played_time': '2'
            }
            res = requests.post('https://api.bilibili.com/x/click-interface/web/heartbeat', 
                              headers=self.headers, data=data)
            if res.json()['code'] == 0:
                return True, None
            else:
                return False, res.json().get('message', '未知错误')
        except Exception as e:
            return False, str(e)
            
    def get_user_info(self):
        """获取用户信息"""
        try:
            res = requests.get('https://api.bilibili.com/x/web-interface/nav',
                headers=self.headers)
            data = res.json()['data']
            return {
                'uname': data['uname'],
                'uid': data['mid'],
                'level': data['level_info']['current_level'],
                'exp': data['level_info']['current_exp'],
                'coin': data['money']
            }
        except:
            return None

    # 新增投币相关方法---------------------------------------
    def get_random_videos(self):
        """获取随机视频列表"""
        try:
            url = "https://api.bilibili.com/x/web-interface/index/top/feed/rcmd"
            params = {'fresh_idx': random.randint(1, 999), 'ps': 20}
            res = requests.get(url, headers=self.headers, params=params)
            if res.status_code == 200:
                return [item['bvid'] for item in res.json().get('data', {}).get('item', [])]
            return []
        except Exception as e:
            logger.error(f"获取随机视频失败：{str(e)}")
            return []

    def check_coin_status(self, bvid):
        """检查视频投币状态"""
        try:
            url = f"https://api.bilibili.com/x/web-interface/coin/video/{bvid}"
            res = requests.get(url, headers=self.headers)
            if res.status_code == 200:
                data = res.json().get('data', {})
                return {
                    'can_coin': data.get('multiply', 0) < 2,  # 最多投2币
                    'is_owner': data.get('is_owner', True)
                }
            return {'can_coin': False, 'is_owner': True}
        except Exception as e:
            logger.error(f"检查投币状态失败：{str(e)}")
            return {'can_coin': False, 'is_owner': True}

    def send_coin(self, bvid):
        """执行投币操作"""
        try:
            url = "https://api.bilibili.com/x/web-interface/coin/add"
            data = {
                'bvid': bvid,
                'multiply': 1,
                'csrf': self.get_csrf()
            }
            res = requests.post(url, headers=self.headers, data=data)
            return res.json().get('code') == 0, res.json().get('message', '未知错误')
        except Exception as e:
            return False, str(e)

    def coin_task(self):
        """投币任务入口"""
        try:
            # 从用户信息获取硬币数量（使用已有逻辑）
            user_info = self.get_user_info()
            if not user_info:
                return False, '无法获取用户信息'
            
            coin_num = user_info['coin']
            target_count = 5 if coin_num >= 5 else 1  # 根据硬币数量设置目标

            success_count = 0
            attempted_bvids = set()

            while success_count < target_count:
                # 获取新一批视频（排除已尝试过的）
                candidates = [bvid for bvid in self.get_random_videos() 
                            if bvid not in attempted_bvids]
                
                if not candidates:
                    candidates = self.get_random_videos()

                for bvid in candidates:
                    if success_count >= target_count:
                        break

                    attempted_bvids.add(bvid)
                    status = self.check_coin_status(bvid)

                    # 校验条件：非自己投稿、可投币
                    if not status['is_owner'] and status['can_coin']:
                        time.sleep(random.uniform(1,3))
                        success, msg = self.send_coin(bvid)
                        if success:
                            logger.info(f"成功为 {bvid} 投币")
                            success_count += 1
                            time.sleep(1)  # 添加间隔防止请求过快
                        else:
                            logger.warning(f"投币失败：{msg}")
                    else:
                        logger.info(f"跳过 {bvid}：不可投币")

                if len(attempted_bvids) > 50:  # 防止无限循环
                    break

            return True, f"成功投币 {success_count}/{target_count} 次"
        except Exception as e:
            return False, str(e)
    # ----------------------------------------------------

def log_info(tasks, user_info):
    """记录任务和用户信息的日志"""
    print('=== 任务完成情况 ===')
    for name, (success, message) in tasks.items():
        if success:
            logger.info(f'{name}: 成功')
        else:
            logger.error(f'{name}: 失败，原因: {message}')
        
    if user_info:
        print('\n=== 用户信息 ===')
        print(f'用户名: {user_info["uname"][0]}{"*" * (len(user_info["uname"]) - 1)}')
        print(f'UID: {str(user_info["uid"])[:2]}{"*" * (len(str(user_info["uid"])) - 4)}{str(user_info["uid"])[-2:]}')
        print(f'等级: {user_info["level"]}')
        print(f'经验: {user_info["exp"]}')
        print(f'硬币: {user_info["coin"]}')

def main():
    # 从环境变量获取cookie
    cookie = os.environ.get('BILIBILI_COOKIE')
    
    # 如果环境变量中没有，则尝试从文件读取(用于本地运行测试)
    if not cookie:
        try:
            with open('cookie.txt', 'r', encoding='utf-8') as f:
                cookie = f.read().strip()
        except FileNotFoundError:
            logger.error('未找到cookie.txt文件且环境变量未设置')
            sys.exit(1)
        except Exception as e:
            logger.error(f'读取cookie失败: {e}')
            sys.exit(1)
    
    if not cookie:
        logger.error('cookie为空')
        sys.exit(1)

    bili = BilibiliTask(cookie)
    
    # 检查登录状态
    login_status, message = bili.check_login_status()
    if not login_status:
        logger.error(f'登录失败，原因: {message}')
        sys.exit(1)
    
    # 执行每日任务
    tasks = {
        '分享视频': bili.share_video(),
        '观看视频': bili.watch_video('BV1rtkiYUEvy'),  # 观看任意一个视频
        '投币任务': bili.coin_task(),  # 新增投币任务
    }
    
    # 获取用户信息
    user_info = bili.get_user_info()
    
    # 记录日志
    log_info(tasks, user_info)

if __name__ == '__main__':
    main()
