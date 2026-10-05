// 图像档位只决定清晰度和抗锯齿，独立保留玩家的阴影、泛光与粒子选择。
const PROFILES=Object.freeze({
  smooth:Object.freeze({maxPixelRatio:1,msaaSamples:0,contactAO:0,aoRadius:18,shadowMapSize:1024,anisotropy:4}),
  balanced:Object.freeze({maxPixelRatio:1.5,msaaSamples:2,contactAO:.35,aoRadius:18,shadowMapSize:1024,anisotropy:8}),
  detailed:Object.freeze({maxPixelRatio:2,msaaSamples:4,contactAO:.55,aoRadius:24,shadowMapSize:2048,anisotropy:8})
});
export function renderProfile(name) { return PROFILES[name]||PROFILES.balanced; }
export function displayPixelRatio(deviceRatio,name) {
  const value=Number(deviceRatio);
  return Math.max(.5,Math.min(Number.isFinite(value)&&value>0?value:1,renderProfile(name).maxPixelRatio));
}
