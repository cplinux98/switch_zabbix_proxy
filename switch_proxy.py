# -*- encoding: utf-8 -*-

"""
@File           :    switch_proxy.py
@Time           :    2022/12/3 22:33
@Author         :    linux98
@Version        :    2.0
@Email          :    cplinux98@gmail.com
@Description    :    

"""
import os
import sys
import logging
from datetime import datetime
from pyzabbix import ZabbixAPI

base_path = os.path.dirname(os.path.realpath(__file__))

# 初始化logger
handlers = [logging.FileHandler(filename=os.path.join(base_path, 'switch_proxy.log'), encoding='utf-8', mode='a+')]

logging.basicConfig(handlers=handlers, level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

server_ip = "192.168.10.61"


def failover(proxy_name):
    try:
        # 记录开始时间
        start_time = datetime.now()
        # 登录zabbix-server
        zapi = ZabbixAPI(f"http://{server_ip}/zabbix")
        zapi.login(api_token="a13bd7cae59138e9b0177c5ffc69ffb1ac5df7c9c6bd7912ec674589b66b57e9")
        # 使用proxy_name获取proxy的id
        failed_proxyid = zapi.proxy.get(filter={"host": proxy_name})[0].get("proxyid")
        # 使用proxy的id获取相关的主机
        wait_switch_hosts = zapi.host.get(filter={"proxy_hostid": failed_proxyid}, output="hostid")
        # 获取故障proxy主机的上的tag
        failed_proxy_tags_list = zapi.host.get(
            filter={"host": proxy_name},
            output="tags",
            selectTags="extend"
        )[0].get("tags")
        backup_proxy_list = []
        for i in failed_proxy_tags_list:
            if i.get("tag") == "backup_proxy":
                backup_proxy_list.append(i.get("value"))

        # 根据tag中的备选proxy主机名列表，获取所有备选proxy的主机id
        backup_proxy_ids_result = zapi.host.get(filter={"host": backup_proxy_list}, output="hostid")
        backup_proxy_ids = [i.get("hostid") for i in backup_proxy_ids_result]
        # 根据所有备选proxy的主机id，获取对应主机的nvps数据
        metrics_list = zapi.item.get(
            hostids=backup_proxy_ids,
            search={"key_": "zabbix[wcache,values]"},
            output=["hostid", "lastvalue"]
        )
        # 对所有备选proxy主机的nvps值进行排序，选择最小的一个来进行切换
        backup_proxy_id = sorted(metrics_list, key=lambda x: x.get("lastvalue"), reverse=False)[0].get("hostid")
        # 根据备选的proxy主机id获取主机名
        backup_proxy_name = zapi.host.get(filter={"hostid": backup_proxy_id}, output=["name"])[0].get("name")
        # 获取对应proxy的id
        backup_proxyid = zapi.proxy.get(filter={"host": backup_proxy_name})[0].get("proxyid")
        # 批量更新所有主机
        switch_proxy_result = zapi.host.massupdate(hosts=wait_switch_hosts, proxy_hostid=backup_proxyid)
        # zabbix-server进程更新配置文件
        server_reload_result = os.popen("/usr/sbin/zabbix_server -R config_cache_reload").read()
        # zabbix-proxy进程更新配置文件
        scripts_id = zapi.script.get(filter={"name": "Reload Proxy Config Cache"},output="extend")[0].get("scriptid")
        proxy_reload_result = zapi.script.execute(scriptid=scripts_id, hostid=backup_proxy_id)
        # 记录结束时间
        end_time = datetime.now()
        # 操作完成后打印日志
        logger.info(f"本次故障切换时间用时: {(end_time - start_time).microseconds} 微秒")
        logger.info(f"本次故障切换详细信息如下:")
        switch_successed_file_path = os.path.join(base_path, f"{datetime.now().strftime('%Y-%m-%d_%H-%M-%S-%f')}-host.txt")
        logger.info(f"当前故障proxy主机为: {proxy_name}")
        logger.info(f"当前选中的备用proxy主机为: {backup_proxy_name}")
        logger.info(f"等待切换的主机列表: {wait_switch_hosts}")
        logger.info(f"最终切换的主机列表: {switch_proxy_result}\n结果已经记录在{switch_successed_file_path}文件内！")
        logger.info(f"zabbix-server进程更新配置文件结果: {server_reload_result}")
        logger.info(f"zabbix-proxy进程更新配置文件结果: {proxy_reload_result}")
        # 记录结果到文件中
        with open(file=switch_successed_file_path, mode="w", encoding="utf-8") as fd:
            fd.write(str(switch_proxy_result))

        return True, None
    except Exception as e:
        logger.error(f"切换失败，错误原因: {e}")
        return False, e


def main_func():
    try:
        arg_list = sys.argv  # filename, failed_proxy
        failed_proxy = arg_list[1]
        logger.info(f"获取的参数列表: {arg_list}")
        result, err = failover(failed_proxy)
        if not result:
            raise RuntimeError(err)
        logger.info(f"切换函数运行结果: {result}, 错误信息: {err}")
    except Exception as e:
        logger.error(e)
        sys.exit(4)


if __name__ == '__main__':
    main_func()
