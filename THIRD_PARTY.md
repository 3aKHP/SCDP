# 来源与许可

SCDP 代码采用 AGPL-3.0-or-later，完整文本见 [LICENSE](LICENSE)。

`src/scdp/official.py` 的路径定位、XOR 和未终结 gzip 流解码方法改编自
[Sallyn0225/eidolon-sc official_cdn.py](https://github.com/Sallyn0225/eidolon-sc/blob/8cdb82b84670466041aed02640bb747f81ddca96/backend/src/eidolon/official_cdn.py)，
固定提交 `8cdb82b84670466041aed02640bb747f81ddca96`。上游作者为 eidolon-sc contributors，
[上游 LICENSE](https://github.com/Sallyn0225/eidolon-sc/blob/8cdb82b84670466041aed02640bb747f81ddca96/LICENSE)
于 2026-11-10 核对。修改包括路径校验、解码容量限制和异常分类。

官方游戏内容及 SCTranslationData 译文具有独立来源身份，不受本仓库代码许可证授权。
原件、工作数据和构建包保存在忽略目录；经验证的文本包通过 GitHub Release 公开分发，消费者 collection 独立控制访问。用途、历史译文许可证据及权利通知入口见 [NOTICE](NOTICE.md)。
测试夹具为自行编写的虚构内容。SCTranslationData 的来源许可与固定快照文件范围在数据任务中单独核对。
