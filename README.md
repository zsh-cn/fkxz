# fkxz-docs — 项目官网

## 项目结构

```
fkxz-docs/
├── index.html                     # 官网主页
├── download.html                  # 下载页面
├── dev.html                       # 文档页面
├── favicon.png                    # 官网图标
├── logo.png                       # 官网大图（导航与首屏，favicon 仅供图标使用）
├── dist/                          # 打包产物（每个 zip 内是单个 exe）
│   ├── wjfk.zip
│   ├── wjfkxz.zip
│   └── wjxz.zip
├── css/                           # 样式文件
│   └── style.css
├── js/                            # 公共脚本
│   └── main.js
├── icons/                         # 程序图标
│   ├── wjfk.ico
│   ├── wjfkxz.ico
│   └── wjxz.ico
└── wjxz/                          # Web 在线下载体验页面
    ├── index.html
    ├── sw.js
    ├── experience.html
    └── favicon.png
```

### 注：dabao.py仅用于验证Release程序安全性，不建议用于生产用途。