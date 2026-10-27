# week 5：建模（优化版）

### 0. 整体思路

- **多优先级人群**：划分为重伤（需要尽快送医）、弱势群体（老人、孕妇等）、健康人群，对应不同的风险等级
- **多起点**：上一次组会已确认是多个起点（区域）
- **多终点**：医院、非医院的庇护所，且有最大容量限制
- **多交通模式**：救护车（只能重伤者乘坐）、直升机（不受路面流量限制）、公交、私家车、地铁（只受地铁网络限制）
- **车辆往返周转**：运送到终点后，再次回到起点
- **动态风险度量**：风险不再是固定值，而是与“暴露在危险环境中的时长”和“该位置的危险程度”成正比。



### 1. 时空网络 (Time-Space Network)

将静态路网 $G$ 扩展为时空路网 $G_T$。

- **节点**：不仅是位置 $i$，而是 $(i, t)$，表示在 $t$ 时刻的节点 $i$。
- **等待**：从 $(i, t)$ 到 $(i, t+1)$ 的边，代表原地等待。
- **往返**：车辆从 $(i, t)$ 到 $(j, t+\tau)$ 卸客后，可以从 $(j, t+\tau)$ 出发空车返回 $(i, t+2\tau)$ 继续接人。



### 2. Notations

| **符号**      | **定义**     | **说明**                                                     |
| ------------- | ------------ | ------------------------------------------------------------ |
| $\mathcal{N}$ | 物理节点集合 | 包含起点、终点、中间路口、地铁站                             |
| $\mathcal{A}$ | 物理路段集合 | 地面道路、地铁轨道、飞机线路                                 |
| $\mathcal{T}$ | 时间步集合   | $t \in \{0, 1, \dots, T_{max}\}$，例如每 5 分钟为一个步长    |
| $\mathcal{K}$ | 人群类别集合 | $k=1$ (重伤，需尽快送医, $k=2$ (弱势，如老人、孕妇等), $k=3$ (普通/健康人群) |
| $\mathcal{M}$ | 交通方式集合 | $m \in \{Amb, Heli, Bus, Car, Sub\}$ (救护车, 直升机, 公交, 私家车, 地铁) |

**子集定义：**

- $\mathcal{R} \subset \mathcal{N}$：灾害起点集合（Origins）。
- $\mathcal{S} \subset \mathcal{N}$：安全终点集合（Destinations）。
  - $\mathcal{S}_{Hosp}$：医院（仅 $k=1$ 可去）。
  - $\mathcal{S}_{Shelter}$：除医院以外的避难所（$k=2,3$ 可去）。
- $\mathcal{A}_{Road}, \mathcal{A}_{Sub}, \mathcal{A}_{Air}$：分别对应地面、地下、空中的路段集合。



### 3. 参数

**网络参数：**

- $C_{ij}^{Road}$：路段 $(i,j)$ 的通行能力（车辆数/单位时间），其中，地面容量会影响公交、救护车、私家车。直升机不受地面同行能力限制，地铁受地铁网络限制
- $\tau_{ij}^m$：交通工具 $m$ 在路段 $(i,j)$ 上的行驶时间（用Time steps来衡量）。
- $Cap_m$：交通工具 $m$ 的载客量（人/车）。

**设施参数：**

- $Cap_i^{Shelter}$：终点节点 $i \in \mathcal{S}$ 的最大容纳人数。

**需求与风险参数：**

- $D_{i}^{k}$：在起点 $i$ 初始时刻滞留的 $k$ 类人群数量。
- $\omega_k$：人群 $k$ 的时间/生命敏感度权重。
- $\rho_{i,t}$：动态风险暴露系数（Risk Exposure Coefficient）。表示在时刻 $t$ 处于节点 $i$ 的单位风险值。
  - *定义逻辑*：例如，洪水水位越高，$\rho_{i,t}$ 越大；安全区则 $\rho_{i,t}=0$。
- $P_{unsat}$：截止 $T_{max}$ 时刻仍未疏散的惩罚基数（Big-M）。

**车辆资源：**

- $V_{i, 0}^m$：初始时刻 $t=0$ 时，节点 $i$ 停有的 $m$ 类车辆数（车辆库存）。



### 4. 决策变量

- **载客流变量** $x_{ij, t}^{k, m}$：表示在时刻 $t$，通过交通工具 $m$，将人群 $k$ 从节点 $i$ 运往 $j$ 的车辆数。
- **空车流变量** $y_{ij, t}^{m}$：表示在时刻 $t$，空载的交通工具 $m$ 从节点 $i$ 开往 $j$ 的车辆数。
- **库存变量** $H_{i, t}^k$：时刻 $t$ 滞留在节点 $i$ 的 $k$ 类人群数量。
- **车辆库存** $E_{i, t}^m$：时刻 $t$ 停在节点 $i$ 的可用 $m$ 类车辆数。



### 5. 目标函数

最小化系统总成本：

$$\min Z = \underbrace{\sum_{t \in \mathcal{T}} \sum_{(i,j) \in \mathcal{A}} \sum_{k \in \mathcal{K}} \sum_{m \in \mathcal{M}} \left( \omega_k \cdot \tau_{ij}^m \cdot x_{ij, t}^{k, m} \cdot Cap_m \right)}_{\text{Z1: 疏散过程中的加权在途时间成本}}$$

$$+ \underbrace{\sum_{t \in \mathcal{T}} \sum_{i \in \mathcal{N}} \sum_{k \in \mathcal{K}} \left( \rho_{i,t} \cdot \omega_k \cdot H_{i, t}^k \right)}_{\text{Z2: 动态风险累积惩罚 (Risk} \times \text{Exposure)}}$$

$$+ \underbrace{\sum_{i \in \mathcal{R}} \sum_{k \in \mathcal{K}} \left( P_{unsat} \cdot \omega_k \cdot H_{i, T_{max}}^k \right)}_{\text{Z3: 加权未完成疏散惩罚}}$$

**解释：**

- **Z1**：路上的时间越短越好，权重 $\omega$ 越大的人群时间越紧迫。

- **Z2**：“风险暴露”的惩罚项。$\sum_t H_{i,t}^k$ 代表人群在节点停留的时长（Exposure Time），乘以 $\rho_{i,t}$ 即为总风险值。如果你在危险的地方呆得越久，或者呆的地方越危险，惩罚就越大。

- **Z3**：加入了 $\omega_k$。意味着如果有重伤员（$\omega_{high}$）没被运走，惩罚会比普通人没被运走大得多。

  

### 6. 约束条件

#### **(1) 人群流守恒**

对每个节点 $i$，每类人 $k$，每个时刻 $t$：

$$H_{i, t}^k = H_{i, t-1}^k - \underbrace{\sum_{j} \sum_{m} (x_{ij, t}^{k, m} \cdot Cap_m)}_{\text{流出（坐车走）}} + \underbrace{\sum_{j} \sum_{m} (x_{ji, t-\tau}^{k, m} \cdot Cap_m)}_{\text{流入（到达）}}$$

- **初始状态**：$H_{i, 0}^k = D_i^k$。
- **解释**：现在的滞留人数 = 上一刻滞留的 - 刚才运走的 + 刚才运到的。

#### **(2) 车辆流守恒与循环**

$$E_{i, t}^m = E_{i, t-1}^m  - \underbrace{\sum_{j} (x_{ij, t}^{\cdot, m} + y_{ij, t}^m)}_{\text{出发（载客+空车）}}  + \underbrace{\sum_{j} (x_{ji, t-\tau}^{\cdot, m} + y_{ji, t-\tau}^m)}_{\text{到达（载客+空车）}}$$

- **解释**：节点现有的车 = 刚才剩下的 - 开走的 + 开回来的。
- **往返机制**：当一辆救护车把人送到医院（$x$流流入医院），下一刻它就变成了医院的可用车辆库存 $E$，模型可以决策让它作为空车流 $y$ 返回起点。

#### **(3) 物理路网容量约束**

地面道路资源是共享的，所有车辆（Bus, Car, Amb）加起来不能堵死。

$$\sum_{k} \sum_{m \in \{Bus, Car, Amb\}} (x_{ij, t}^{k, m} + y_{ij, t}^m) \le C_{ij}^{Road}, \quad \forall (i,j) \in \mathcal{A}_{Road}$$

- **注意**：直升机和地铁不占用此约束（它们有自己的 $C_{ij}^{Air}, C_{ij}^{Sub}$）。

#### **(4) 车辆类型约束**

- **救护车专用——只有重伤员 ($k=1$) 能坐救护车 ($m=Amb$)**：$x_{ij, t}^{k, Amb} = 0, \quad \forall k \neq 1$

- **目的地约束**：$x_{ij,t}^{k,m} = 0 \quad \text{if } j \text{ is destination and } j \notin \text{Dest}(k)$

  救护车必须去医院。如果 $j \notin \mathcal{S}_{Hosp}$ 且 $j$ 不是中间路口，则流量为0。

- **地铁隔离**：地铁仅在地铁网络 $\mathcal{A}_{Sub}$ 运行。

#### **(5) 车辆库存限制**

派出的车辆数不能多于现有的车辆数。

$$\sum_{j} (x_{ij, t}^{\cdot, m} + y_{ij, t}^m) \le E_{i, t-1}^m$$

#### **(6) 避难所容量限制**

对于所有属于安全终点的节点，任一时刻滞留的人数不得超过其容量：

$$\sum_{k \in \mathcal{K}} H_{i, t}^k \le Cap_i^{Shelter}, \quad \forall i \in \mathcal{S}, \forall t \in \mathcal{T}$$





### 附录：完整模型 

$$\boxed{ \begin{aligned} \min \quad & \underbrace{\sum_{t, (i,j), k, m} \omega_k \tau_{ij}^m Cap_m x_{ij,t}^{k,m}}_{Z_1} + \underbrace{\sum_{t, i, k} \rho_{i,t} \omega_k H_{i,t}^k}_{Z_2} + \underbrace{\sum_{i, k} P_{unsat} \omega_k H_{i, T_{max}}^k}_{Z_3} \\[15pt] \text{s.t.} \quad & H_{i,t}^k = H_{i,t-1}^k - \sum_{j,m} Cap_m x_{ij,t}^{k,m} + \sum_{j,m} Cap_m x_{ji, t-\tau_{ji}^m}^{k,m} & \forall i, k, t > 0 \quad \text{(C1)} \\ & H_{i,0}^k = D_i^k & \forall i \in \mathcal{R}, k \quad \text{(C2)} \\ & E_{i,t}^m = E_{i,t-1}^m - \sum_{j} \left( \sum_k x_{ij,t}^{k,m} + y_{ij,t}^m \right) + \sum_{j} \left( \sum_k x_{ji, t-\tau}^{k,m} + y_{ji, t-\tau}^m \right) & \forall i, m, t > 0 \quad \text{(C3)} \\ & E_{i,0}^m = V_{i,0}^m & \forall i, m \quad \text{(C4)} \\ & \sum_{j} \left( \sum_{k} x_{ij,t}^{k,m} + y_{ij,t}^m \right) \leq E_{i,t-1}^m & \forall i, m, t \quad \text{(C5)} \\ & \sum_{k} \sum_{m \in \mathcal{M}_{road}} \left( x_{ij,t}^{k,m} + y_{ij,t}^m \right) \leq C_{ij}^{road} & \forall (i,j) \in \mathcal{A}_{road}, t \quad \text{(C6)} \\ & x_{ij,t}^{k,m} = 0 & \forall (k,m) \in \mathcal{I}_{incomp} \quad \text{(C7)} \\ & x_{ij,t}^{k,m} = 0 & \forall j \notin \text{Dest}(k) \cup \mathcal{N}_{inter} \quad \text{(C8)} \\ & \sum_{k} H_{i,t}^k \leq Cap_i^{Shelter} & \forall i \in \mathcal{S}, t \quad \text{(C10)} \\ & x_{ij,t}^{k,m}, y_{ij,t}^m, E_{i,t}^m \in \mathbb{Z}^+; \quad H_{i,t}^k \geq 0 & \forall i,j,k,m,t \quad \text{(C11)} \end{aligned} }$$



### Notations汇总

#### 1. 集合 

- $\mathcal{N}, \mathcal{A}, \mathcal{T}$: 物理节点集、路段弧集、离散时间步集合。
- $\mathcal{R}, \mathcal{S}$: 灾害起点集合（Origins）、安全终点集合（Destinations）。
- $\mathcal{K}$: 人群类别集合（$k=1$: 重伤, $k=2$: 弱势, $k=3$: 健康）。
- $\mathcal{M}$: 交通模式集合（$Amb, Bus, Car, Heli, Sub$）。
- $\mathcal{M}_{road}$: 占用地面道路资源的交通工具子集（$\subset \mathcal{M}$，如公交、私家车、救护车）。
- $\mathcal{I}_{incomp}$: 不兼容配对集合（如 $k=\text{健康}$ 与 $m=\text{救护车}$ 不兼容）。
- $\text{Dest}(k)$: 第 $k$ 类人群的合法目的地集合（如重伤员只能去 $\mathcal{S}_{Hosp}$）。

#### 2. 参数 

- $C_{ij}^{road}$: 地面路段 $(i,j)$ 的最大通行能力（单位：辆/时间步）。
- $Cap_m$: 交通工具 $m$ 的载客容量（单位：人/车）。
- $Cap_i^{Shelter}$: 终点节点 $i$ 的最大容纳人数（避难所容量）。
- $\tau_{ij}^m$: 交通工具 $m$ 在路段 $(i,j)$ 上的行驶时间步数。
- $\rho_{i,t}$: 动态风险暴露系数（节点 $i$ 在时刻 $t$ 的单位风险强度）。
- $\omega_k$: 第 $k$ 类人群的时间/生命敏感度权重。
- $D_i^k$: 初始时刻起点 $i$ 滞留的 $k$ 类人群数量。

#### 3. 决策变量

- $x_{ij,t}^{k,m}$: **载客车流**（在 $t$ 时刻，模式 $m$ 载着人群 $k$ 从 $i$ 出发的车辆数）。
- $y_{ij,t}^{m}$: **空驶车流**（在 $t$ 时刻，模式 $m$ 空车从 $i$ 出发调度的车辆数，用于车辆回流）。
- $H_{i,t}^k$: **人员滞留量**（在 $t$ 时刻，节点 $i$ 等待疏散的人群 $k$ 数量）。
- $E_{i,t}^m$: **车辆库存量**（在 $t$ 时刻，停靠在节点 $i$ 可用的模式 $m$ 车辆数）。

#### 4. 关键约束解释

- **(C1-C2) 人员流动守恒**：动态库存平衡方程（当前滞留 = 之前滞留 - 运走的 + 运到的）。
- **(C3-C5) 车辆流动守恒**：车辆在时空网络中的循环逻辑（包含载客 $x$ 和空驶 $y$ 的状态转换），并确保派出的车辆不超过当前节点的车辆库存。
- **(C6) 共享路网容量**：限制所有地面交通工具（公交、私家车、救护车）的总流量不超过路段 $C_{ij}^{road}$，防止拥堵溢出。
- **(C7-C8) 业务逻辑约束**：强制执行“人群-车辆”兼容性（如健康人不能坐救护车）及“人群-终点”匹配性（如重伤员必须去医院）。
- **(C10) 避难所容量约束**：确保任一时刻进入终点 $i$ 的总人数不超过其物理容量 $Cap_i^{Shelter}$。