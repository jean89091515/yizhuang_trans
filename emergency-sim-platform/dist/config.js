/**
 * 运行时配置 —— 部署后可直接编辑本文件，无需重新构建前端。
 */
window.EMERGENCY_SIM_CONFIG = {
  // 平台标题（与一体化平台保持一致）
  title: '宏中微一体化交通计算示范平台',
  subtitle: '北京亦庄 重大突发事件下交通流传播运行',

  map: {
    // 底图（地图右下角“图层”按钮切换，第一项为默认）。默认高德在线瓦片；
    // 若平台已有统一底图服务或服务器无外网，替换 url 即可（内网瓦片同样支持 {s}{x}{y}{z} 模板）。
    //   url         瓦片地址；overlayUrl 叠加的注记/路网瓦片（可选）
    //   darkFilter  对浅色瓦片做深色化滤镜，贴合大屏风格；filter 可直接写 CSS filter
    // 所有底图须与 coord 坐标系一致：'gcj02'（高德/腾讯）或 'wgs84'（天地图/OSM 等），叠加图层自动由 WGS84 转换。
    // 道路、地铁矢量图层来自 data/basemap.json（导出脚本生成），与底图无关，无外网时也能显示。
    basemaps: [
      { id: 'dark', name: '深色街道', url: 'https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}', darkFilter: true },
      { id: 'satellite', name: '卫星影像', url: 'https://webst0{s}.is.autonavi.com/appmaptile?style=6&x={x}&y={y}&z={z}',
        overlayUrl: 'https://webst0{s}.is.autonavi.com/appmaptile?style=8&x={x}&y={y}&z={z}', filter: 'brightness(0.62) saturate(0.8)' },
      { id: 'light', name: '标准街道', url: 'https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}', filter: 'brightness(0.85)' },
      { id: 'none', name: '无底图', url: '' },
    ],
    subdomains: ['1', '2', '3', '4'],
    coord: 'gcj02',
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

  // 打开页面后自动运行一次基准场景（URL 参数 autorun=0/1 可覆盖）
  autoRun: true,

  // “返回首页”按钮地址；留空则不显示。独立页面部署时可设为 '/traffic-screen/#/home'；
  // iframe 嵌入时点击会向父页面发送 { type: 'emergency-sim:back' }
  homeUrl: '',
}
