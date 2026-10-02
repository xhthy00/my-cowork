# 蓝色小牛眨眼帧

内置 image_gen 编辑 `app-logo.png`，生成 `renderer/src/assets/brand/cow-blink-blue-closed.png`。启动页只在眼部使用闭眼帧遮罩，每 3.8 秒眨眼两次；其余区域沿用原图，避免整张图切换时抖动。减少动态效果时只展示睁眼原图。原 `cow-blink.webp` 保留。

## 最终提示词

Use case: precise-object-edit. Edit target: supplied blue 3D cow app icon. Produce a CLOSED-EYES animation frame for this exact icon. Change ONLY the two eyes: gently close BOTH eyelids for a natural happy blink, smooth curved dark blue-slate eyelid seams at original eye centers. Eyes completely closed, no pupils, no white eyeballs visible. Preserve everything else EXACTLY pixel-aligned to the original reference: identical canvas, icon size and bounding box, head placement, head shape, muzzle, smiling mouth, eyebrows, eye patch, ears, horns, tuft, lighting, blue rounded-square background, shadows and transparent outside tile. Do not recenter, zoom, change head pose, move eyebrows, reshape head or recolor. Closed lids must be inside original eyeball shapes at about x45.5% and x60.5%, y56% of canvas, the surrounding skin/eye patch unchanged. This will be overlaid on original for animation, so placement MUST match. Same softly sculpted 3D style and palette. Full square icon with transparency outside rounded corners, no text or added symbols.

