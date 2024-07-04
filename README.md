## 雅图伴侣 Home Assistant 集成组件

本组件实现雅图伴侣运行数据 在Home Assistant 中展示。

### 安装
1、在 Home Assistant 的 custom_components 目录下新建一个 airtub_udp 目录，然后将本项目所有文件复制到新建的 airtub_udp 目录下。

2、在 configuration.yaml 中添加如下配置：
```yaml
airtub_udp:
    multicast_group: "224.0.1.3"
    multicast_port: 4211
    device: "your_device_serial"
    secret: "your_secret_key"
```
其中 device 为注册壁挂炉序列号，secret 为注册壁挂炉密钥。

3、重启 Home Assistant。

### 使用

重启 Home Assistant 后，可以在【配置】- 【设备与服务】-【实体】中找到 sensor.boiler_[device]_xxx 的实体，其中 device 为配置中的 device 值。

_xxx 的各项解释如下：
```
"flt": 故障状态 0-无故障 其它故障见雅图伴侣小程序的故障帮助
"fst": 火焰状态 0-未点火、1-点火
"mod": 当前燃气比例阀开度 0-100%
"cct": 当前采暖水温度
"cdt": 当前生活热水温度
"ccm": 当前采暖状态 0-未开启、1-开启
"cdm": 当前生活热水状态 0-未开启、1-开启
"tct": 目标采暖水温度
"tdt": 目标生活热水温度
"tcm": 目标采暖水模式 0-未开启、1-开启
"tdm": 目标生活热水模式 0-未开启、1-开启
"atm": 自动室温调节模式 0-未开启、1-开启
"odt": 当前室外温度
"coe": 当前采用的室外温度补偿系数
"crt": 当前室温
"trt": 目标室温
"pwr": 外置传感器当前电量
"sch": 自动任务状态 0-未开启、1-开启
"vir": 屏蔽高温杀菌模式 0-未开启、1-开启(仅系统炉)
"tdf": 生活水启停温差(仅系统炉)
```