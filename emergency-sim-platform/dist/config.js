/**
 * 运行时配置 —— 部署后可直接编辑本文件，无需重新构建前端。
 */
window.EMERGENCY_SIM_CONFIG = {
  // 平台标题（与一体化平台保持一致）
  title: '宏中微一体化交通计算示范平台',
  subtitle: '北京亦庄 重大突发事件下交通流传播运行',

  // 底图：默认高德栅格瓦片（GCJ-02 坐标，叠加图层会自动由 WGS84 转换）
  // 若平台已有统一底图服务，替换 tileUrl / subdomains / coord 即可；
  // coord 取 'gcj02'（高德/腾讯）或 'wgs84'（天地图/OSM 等）
  map: {
    tileUrl: 'https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}',
    subdomains: ['1', '2', '3', '4'],
    coord: 'gcj02',
    darkFilter: true, // 对浅色瓦片做深色化滤镜，贴合大屏风格
    center: [116.494, 39.745], // WGS84 [lon, lat]
    zoom: 13,
    minZoom: 9,
    maxZoom: 18,
  },

  // 数据目录（相对 index.html）
  dataBase: './data/',

  // 服务端求解器地址（求解器选择“服务端求解”时使用）；同域部署可留空
  apiBase: '',

  // 计算过程展示：每个阶段最短展示时长（ms），便于观察计算流程；0 表示不延时
  stageDelayMs: 450,

  // 打开页面后自动运行一次基准场景
  autoRun: true,
}
