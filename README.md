# 土地、家族与周期：底层农业社会模拟

[![Tests](https://github.com/wilmerfranzenqaq-dot/agrarian-society-simulator/actions/workflows/tests.yml/badge.svg)](https://github.com/wilmerfranzenqaq-dot/agrarian-society-simulator/actions/workflows/tests.yml)
[![Release](https://img.shields.io/github/v/release/wilmerfranzenqaq-dot/agrarian-society-simulator)](https://github.com/wilmerfranzenqaq-dot/agrarian-society-simulator/releases/latest)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

这是一个观察者视角的代理模型。它不模拟皇帝，不提供赈灾、军事、科技等经营按钮，也没有随机灾害或隐藏 Buff。宏观结构只来自少数底层约束：

1. 土地和劳动共同产生粮食，边际产出递减。
2. 每个人每年必须消耗最低口粮；短缺提高死亡率。
3. 生育需要真实粮食成本，并受家庭储备策略约束。
4. 多余土地进入租佃市场，多余劳动获得租地；产出按固定比例分租。
5. 储备不足的家庭卖地，拥有剩余的家庭按自身购地倾向买地。
6. 每隔一代发生继承。均分会碎片化土地，长子继承会制造无地支系。
7. 饥饿、维持自耕所需土地的缺口和土地不平等形成逐户生存压力。压力会逐年累积或消退，避免一次继承冲击立即变成全国起义；累积值超过各家反抗阈值的人口形成集体动员。
8. 总压力超过制度阈值即发生起义。参与程度越高，冲突死亡风险越高，胜利后获得土地的权重也越高；因此反抗策略同样存在可被选择的成本与收益。
9. 集中土地被没收并重新分配后，土地再度开始分化，形成下一周期。

土地在生产、交易、继承和起义中严格守恒。税收直接退出家庭部门，模型不假设国家如何使用它。

## 两种模式

### 固定规则

所有家庭使用同一套生育、存粮、购地和继承策略。适合做控制变量实验，例如：

- 均分继承与长子继承的长期差异；
- 不同产出税率或租佃分成如何改变人口和土地集中；
- 起义阈值与没收比例如何改变周期长度。

### 策略演化

初始家庭拥有随机策略。每次继承时，后代复制父代策略并有小概率变异。模型没有替代理做全知最优化；策略的“最优”由达尔文选择定义：一种策略如果能留下更多存活后代，它在总人口中的占比就会上升。

可演化基因包括：

- 生育倾向；
- 目标存粮年数；
- 用剩余购买土地的比例；
- 参加集体行动的物质压力阈值；
- 选择均分继承或长子继承（二元选择，后代继承该选择，变异时可能翻转）。

界面用一根人口比例条显示选择均分继承和长子继承的人口各占多少，并显示其他策略的人口加权均值与最大存续谱系。人口/家户、土地结构、生存/起义和策略分别绘图；土地直方图逐档标明亩数范围。起义改变资源环境后，策略占比可能重新调整并收敛到新的范围。

## 运行

要求 Python 3.10+ 和 Tkinter，不需要第三方包。

```bash
python3 main.py
```

macOS 也可以双击 `run.command`。

命令行批量实验：

```bash
python3 main.py --years 500 --mode fixed --inheritance equal --tax 0.12
python3 main.py --years 500 --mode evolution --mutation 0.06 --csv evolution.csv
```

运行测试：

```bash
python3 -m unittest -v
```

测试覆盖土地严格守恒、固定策略不漂移、演化可复现、起义再分配、数值稳定和 CSV 导出。

## 如何理解结果

本项目追求的是“机制透明”，而不是宣称还原全部古代历史。参数决定的是一个明确的反事实世界。历史写实度应通过真实人口、亩产、口粮、租率、税率和继承数据逐步校准，而不应靠加入更多不可检验的事件修正项。
