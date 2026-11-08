# v3 SFT 数据预览

train 396 条

## 分类统计

- reply:comment: 107
- reply:dialog: 109
- tool:get_item_detail: 19
- tool:image_search: 37
- tool:list_categories: 19
- tool:text_search: 105

## tool:text_search

- 输入：`找耐高温双层玻璃杯带勺`
  输出：`{"action":"tool","tool":"text_search","arguments":{"query":"耐高温双层玻璃杯带勺","category":"水杯","top_k":8},"say":"稍等，我找一下"}`

- 输入：`找深灰色的男装`
  输出：`{"action":"tool","tool":"text_search","arguments":{"query":"深灰色的男装","category":"男装","top_k":5}}`


## tool:image_search

- 输入：`想问一下，我传的图是什么类，找同款`
  输出：`{"action":"tool","tool":"image_search","arguments":{"alpha":0.6}}`

- 输入：`帮我看图找相似商品`
  输出：`{"action":"tool","tool":"image_search","arguments":{"alpha":0.6}}`


## tool:list_categories

- 输入：`库里有什么商品`
  输出：`{"action":"tool","tool":"list_categories","arguments":{}}`

- 输入：`请问支持哪些品类`
  输出：`{"action":"tool","tool":"list_categories","arguments":{}}`


## tool:get_item_detail

- 输入：`上一轮检索结果： / 1. 女士帆布高帮运动鞋（id=muge_420197） / 2. 男士皮鞋 商务正装 棕色（id=muge_47460） / 3. 啄木鸟纯棉短袖t恤男士黑色夏季202（id=12449743996） / 第2个是什么材质`
  输出：`{"action":"tool","tool":"get_item_detail","arguments":{"item_id":"muge_47460"}}`

- 输入：`上一轮检索结果： / 1. 正品男装春秋新款男装中年男士夹克外套（id=10608053339） / 2. 陶瓷杯高杯（id=muge_287518） / 3. 猎豹 户外多功能双肩包旅行包登山包 （id=12449307268） / 第2个是什么材质`
  输出：`{"action":"tool","tool":"get_item_detail","arguments":{"item_id":"muge_287518"}}`


## reply:comment

- 输入：`用户想要米白色短款连帽拉链卫衣，检索结果： / {"items":[{"item_name":"秋冬新款长袖拉链连帽卫衣女装韩版宽松ins学生短款外套上衣","type":"短款连帽拉链卫衣","color":"米白色","material":"未识别","similarity":0.51},{"item_name":"统狮男装运动套装 Y7 套 下单备注颜色 下单备注尺码","type":"运动`
  输出：`{"action":"reply","text":"这几款以米白色、白色为主，短款连帽拉链卫衣、运动套装居多，风格偏日常；其中 1 款标了材质（加绒面料），其余未标注。相似度都在 0.43 以上。"}`

- 输入：`用户想要中长款针织毛衣裙，检索结果： / {"items":[{"item_name":"免费试穿正品羊绒衫女士毛衣女打底衫新款修身显瘦羊毛衫女中长款针织衫专柜正品品牌羊绒衫女漂亮半高圆领","type":"中长款针织毛衣裙","color":"米色","material":"羊绒","similarity":0.49},{"item_name":"半高领插肩袖元宝针山羊绒女长袖宽松保暖毛衣时尚百`
  输出：`{"action":"reply","text":"这几款以米色、紫色为主，中长款针织毛衣裙、针织衫居多，风格偏日常；其中 3 款标了材质（羊绒），其余未标注。相似度都在 0.46 以上。"}`


## reply:dialog

- 输入：`谢谢`
  输出：`{"action":"reply","text":"不客气，需要找别的随时说。"}`

- 输入：`刚才那个再看下`
  输出：`{"action":"reply","text":"可以点上方卡片查看详情，也可以把商品名告诉我再查。"}`


## reply:with_context
