# fkxz-docs — 项目官网

## 项目结构

```
fkxz-docs/
├── index.html                     # 官网主页
├── download.html                  # 下载页面
├── dev.html                       # 文档页面
├── share.html                     # 分块文件分享落地页（独立单页，不进入官网导航）
│                                  # 通过 ?fkx=<清单地址> 解析并展示文件信息，引导下载桌面程序
├── README.md                      # 官网维护说明
├── dabao.py                       # Release 程序安全性验证脚本
├── favicon.png                    # 官网图标
├── logo.png                       # 官网大图（导航与首屏，favicon 仅供图标使用）
├── dist/                          # 打包产物（每个 zip 内含同名程序文件夹）
│   ├── wjfk.zip                   # 解压为 wjfk/（wjfk.exe 与 _internal/）
│   ├── wjfkxz.zip                 # 解压为 wjfkxz/（wjfkxz.exe 与 _internal/）
│   └── wjxz.zip                   # 解压为 wjxz/（wjxz.exe 与 _internal/）
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