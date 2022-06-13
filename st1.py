
import numpy as np
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
from collections import defaultdict
import requests
import json
import time
from geopy import distance
import requests
import urllib.parse
import folium
from streamlit_folium import st_folium
import streamlit.components.v1 as components
import networkx as nx
from geopy.geocoders import Nominatim
geolocator = Nominatim(user_agent="streamlit_application_last_task")
with st.echo(code_location='below'):
    st.set_page_config(layout="wide")
    st.title("Проект 'Анализ ассортимента сети розничных магазинов'")
    st.subheader("Идея:")
    st.write("используя мобильное приложение \"Красного и белого\", составить оптимальный маршрут для совершения покупок")
    st.subheader("Технологии и методы программирования, используемые в проекте")
    st.write("""- *`fiddler proxy`* - установка сертификата на телефон для перехвата данных от приложения к серверу (оттуда были получены заголовки запроса для функции `get_req_by_cat`)

- *`ООП`* - данные сохраняются в python-овские объекты, с которыми в дальнейшем можно удобно работать

Список классов:

    - *Good* - представляет собой товар с различными параметрами (цена, остаток в магазине и тд)

    - *Shop* - магазин, имеет координаты, адрес и список товаров

Также отличительной особенностью являлось то, что в приложении "Красного и белого" по умолчанию отображаются не все цены. Часть из них скрыты плашкой "Доступно только в розничном магазине", но по api они доступны. Со стороны сервера, такие товары возвращаются с меткой `"hidden"` и ценой, деленной на тысячу (1000), таким образом, на клиенте ее постфактум можно восстановить. 
    """)
    st.subheader("Легенда")
    st.write("""Давайте представим, что нам нужно решить конкретную задачу: проехаться по адресу из точки А в точку B и по дороге заехать в магазин. Допустим, мы едем на свидание, и нам нужно выбрать такой магазин, в котором будет алкоголь, фрукты и десерт, при этом стоимость этих продуктов будет максимальной (мы же хотим произвести хорошее впечатление, не так ли? 😏)""")

    def get_coordinates_by_adress(address):
        """
        получить адрес по тексту используя данные из OpenStreetMap
        NOTE: загружайте данные в виде "улица X, 1", с запятой и текстом "улица"
        """
        address = f'Москва, {address}'
        #         url = 'https://nominatim.openstreetmap.org/search/' + urllib.parse.quote(address) +'?format=json'
        #         response = requests.get(url).json()
        try:
            location = geolocator.geocode(address)
        except Exception as e:
            print(e)
            return None

        if location:
            lat = location.latitude
            lon = location.longitude
            description = location.address
            return Point(lat=float(lat), lon=float(lon), description=description)   

    @st.cache(allow_output_mutation=True)
    def get_req_by_cat(cat_id, city_id=5561, shop_id=5983):
        """получить все магазины определенной категории"""
        headers = {
            "Host":"retail-kb.itnap.ru",
            "Accept":"*/*",
            "Accept-Language":"ru",
            "Connection":"keep-alive",
            "Accept-Encoding":"gzip, deflate, br",
            "User-Agent":"RedWhite/2.18.3 (iPhone 7; iOS 14.0.1; 1; 3494A92F-1B3A-4A2C-80D5-71B9F88B1BCC)",
        }

        request = f"https://retail-kb.itnap.ru/api/v1/products?category_id={cat_id}&city_id={city_id}&limit=100000&offset=0&q_f%5B9999%5D%5B%5D=2&shop_id={shop_id}&sort=min"
        request_result = json.loads(requests.get(request, headers=headers, verify=False).text)
        return Good.from_kb(request_result)

    categories = { # список категорий товаров, также из приложения
        100002: "Вино импорт",
        101013: "Вино Россия",
        100085: "Вино игристое, Вермут",
        100087: "Водка, Настойки",
        100011: "Виски, Бурбон",
        100091: "Коньяк, Арманьяк",
        100114: "Текила, Ром, Ликер",
        100095: "Соки, Воды",
        101024: "Фрукты и овощи",
        100101: "Шоколад, Конфеты"
    }

    class Good(): # объект типа товар
        def __init__(self, name, count, price, is_hidden, json_dict):
            self.name = name
            self.count = count
            self.price = price
            self.is_hidden = is_hidden
            self.json_dict = {**json_dict}
            self.json_dict['price'] = price

        def __getattr__(self, attr): # некоторые атрибуты с подчеркиванием
            if attr.startswith("_0"):
                attr = attr[2:]
                return self.json_dict[attr]
            else:
                return super().__getattr__(attr)

        
        @classmethod
        def from_kb(cls, json_res):
            """конструктор объекта из json
            приложение "Красного и белого" очень хитрое - оно скрывает некоторые цены, и помечает их специальным флагом (вероятно, чтобы они не отображались в приложении)
            недостаток этого метода заключается в том, что и флаг и цена приходят в одном словаре!
            разработчики сервиса учли этот факт, и добавили дополнительный слой защиты -- для скрытых товаров цена делится на 1000

            переменная 'real_price' является результатом приведения скрытой цены к реальной (есил видим флаг - домножаем на 1000)
            """
            res = []
            for product in json_res['result']['products']:
                real_price = product['price']*1000 if product['hidden_buy_price'] else product['price']
                
                res.append(Good(
                    name=product['name'],
                    count=product['shop_quantity'],
                    price=real_price,
                    is_hidden=product['hidden_buy_price'],
                    json_dict=product
                ))
            return res

    class Shop():
        def __init__(self, latitude, longitude, address, shop_id, schedule):
            """объект класса магазин, имеет координаты адрес id и расписание работы"""
            self.latitude = latitude
            self.longitude = longitude
            self.address = address
            self.shop_id = shop_id
            self.schedule = schedule

        @classmethod
        def from_kb(cls, json_res):
            """конструктор из результата запроса"""
            res = []
            for shop in json_res['result']['shops']:
                res.append(Shop(
                    latitude=float(shop['latitude']),
                    longitude=float(shop['longitude']),
                    address=shop['name'],
                    shop_id = shop['shop_id'],
                    schedule= shop['schedule']
                ))
            return res
        
        
        @property
        def point(self):
            """объект точка для магазина"""
            return Point(lat=float(self.latitude), lon=float(self.longitude), description = f"КБ {self.address}")

        
        @property
        def all_goods(self):
            """получить все товары конкретного магазина"""
            ### вычисляется один раз, потом переиспользуется
            if not hasattr(self, "_all_goods") or not self._all_goods:
                self._all_goods = {}
                for index, category_id in enumerate(categories):
                    goods = get_req_by_cat(
                        category_id, # id категории, описание в словаре categories
                        city_id=664, # id для Москвы
                        shop_id = self.shop_id
                    )
                    self._all_goods[category_id] = goods
                    time.sleep(0.3)
            return self._all_goods
    

    class Point():
        def __init__(self, lon, lat, description):
            """геоточка - координаты и описание"""
            self.lon = lon
            self.lat = lat
            self.description = description
        
        def __repr__(self):
            return f"<Point {self.description=}>"
        @property
        def point(self):
            return (self.lat, self.lon)
        
        def distance(self, other):
            """вычислить геодистанцию"""
            return distance.geodesic(self.point, other.point).km
    

    st.text("""
        Сначала введем точку отправления и точку назначения, после чего определим от 1 до 5 магазинов, находящихся по пути.
    """)

    st.info("Обратите внимание: улицы нужно вводить в формате 'улица Советская, 1', со словом 'улица' и номером дома. \nЕсли ввести адрес неправильно, корректная работа не гарантируется, так как для получения информации используется движок Nominatim из пакета OpenStreetMap, который достаточно чувствителен к входным данным.")
    with open("./moscow_shops.json", "r") as f:
        # moscow_shops -- получен из анализа запроса
        kb_dict = json.load(f)
        
    shops = Shop.from_kb(kb_dict)

    address1 = st.text_input("Введите Ваш адрес", ' улица Земляной вал, 41')
    start = get_coordinates_by_adress(address1)
    st.write(f"Ваш адрес на OpenStreetMap: {start.description}")
    
    address2 = st.text_input("Введите адрес назначения", "Дмитровское шоссе, 15")
    dest = get_coordinates_by_adress(address2)
    st.write(f"Конечная точка маршрута на OpenStreetMap: {dest.description}")

    def select_closest_shop(point1, point2, shops, n=5):
        if isinstance(point1, str):
            point1 = get_coordinates_by_adress(point1)
        if isinstance(point2, str):
            point2 = get_coordinates_by_adress(point2)
        shops = sorted(shops, key=lambda x: point1.distance(x.point) + point2.distance(x.point))
        return shops[:n]
    n_shops = st.number_input("Выберите количество магазинов для поиска (желательно не больше 5, иначе парсинг долго работает)", 1, 10, value=3)
    closest_shops = select_closest_shop(start, dest, shops, n=n_shops)
    # центр карты
    center = ((start.point[0] + dest.point[0])/2, (start.point[1] + dest.point[1])/2)
    m = folium.Map(center, zoom_start=12)
    folium.Circle(start.point,radius=50, tooltip=start.description, color="red").add_to(m)
    folium.Circle(dest.point,radius=50, tooltip=dest.description, color="red").add_to(m)

    for index, shop in enumerate(closest_shops, 1):
        description = f"""({index})
        
    Адрес: {shop.address}

    Расстояние, КМ: {start.distance(shop.point) + dest.distance(shop.point)}
    """
        folium.Circle(shop.point.point,radius=30, tooltip=description, color="blue").add_to(m)
    st.write("Точки на карте (синие - магазины, красные - точки отправления и прибытия)")
    st_m =  st_folium(m, width = 700, height=500)
    # st.write(st_m)

    st.subheader("Работа с данными")
    # инициализация может занимать много времени, подождите пожалуйста
    for shop in closest_shops:
        print(shop.all_goods)
        st.info(f"Данные по магазину по адресу '{shop.address}' успешно загружены")

    ### получаем датасет из всех продуктов в магазинах
    def shop_df(shop):
        df = pd.DataFrame([{'category_id': category, **good.json_dict} for category in shop.all_goods for good in shop.all_goods[category]])
        df['category_name'] = df['category_id'].apply(categories.get)
        df['shop_id'] = shop.shop_id
        return df
    all_dfs = [shop_df(shop) for shop in closest_shops]
    df = pd.concat(all_dfs)
    
    reverse_categories = {v:k for k,v in categories.items()}

    st.write("Посмотрим, отличается ли между собой ассортимент этих магазинов в отдельных категориях")
    st.write("- Вино импорт")
    st.write("- Водка, настойки")
    st.write("- Фрукты и овощи")
    st.write("- Виски, Бурбон")
    st.write("- Текила, Ром, ликер")

    human_readable_categories = ['Вино импорт', 'Водка, Настойки', 'Фрукты и овощи', 'Виски, Бурбон', 'Текила, Ром, Ликер']
    selected_categories = [reverse_categories[key] for key in human_readable_categories]
    counted_categories = df[df['category_id'].isin(selected_categories)].groupby(['category_id', 'shop_id'])['product_id'].count().to_dict()
    category_data = defaultdict(dict)
    data = []
    for (cat_id, shop_id), count in counted_categories.items():
        category_data[shop_id][cat_id] = count
    data = []
    for shop_id in category_data:
        data.append([shop_id, *category_data[shop_id].values()])
    data_df = pd.DataFrame(data, columns = ['shop_id', *human_readable_categories])
    data_df['address'] = data_df['shop_id'].apply(lambda x: next(shop for shop in shops if shop.shop_id==int(x)).address)
    fig, ax = plt.subplots()
    for cat in ['Вино импорт', 'Водка, Настойки', 'Фрукты и овощи', 'Виски, Бурбон', 'Текила, Ром, Ликер']:
        plt.barh(y=data_df['address'], width=data_df[cat], label=cat)
    plt.legend()
    st.pyplot(fig)
    st.write("Как видим, ассортимент не слишком сильно отличается, и можно выбирать любой магазин")







    st.write("Давайте выберем такой магазин, в котором стоимость товаров из нашего условного набора будет максимальной")

    # получили id по категории
    whiskey_cat = reverse_categories['Виски, Бурбон']
    fruit_cat = reverse_categories['Фрукты и овощи']
    choco_cat = reverse_categories['Шоколад, Конфеты']

    # узнали максимальные цены для каждого товара из этой категории (ключ - магазин, значение - максимальная цена товара этой категории в этом магазине)
    whiskey_prices = df[df['category_id'] == whiskey_cat][['shop_id', 'price']].groupby('shop_id').max()
    fruit_prices = df[df['category_id'] == fruit_cat][['shop_id', 'price']].groupby('shop_id').max()
    choco_prices = df[df['category_id'] == choco_cat][['shop_id', 'price']].groupby('shop_id').max()

    # получаем датасет (цена на виски, цена на фрукт, цена на шоколад)
    all_df = pd.merge(whiskey_prices, fruit_prices, on='shop_id')
    all_df = pd.merge(all_df, choco_prices, on='shop_id')
    all_df.columns = ['whiskey_price', 'fruit_price', 'choco_price']
    
    # суммируем 
    all_df['total'] = all_df['whiskey_price'] + all_df['fruit_price'] + all_df['choco_price']
    
    # и берем магазин, у которого цена максимальная
    max_price = all_df['total'].max()
    top_price_shop_id = next(shop_id for shop_id, price in all_df.to_dict()['total'].items() if price==max_price)
    top_price_shop = next(shop for shop in shops if shop.shop_id == top_price_shop_id)

    # теперь выбираем объекты товара из этого магазина, цены которых максимальны и соответствуют нашим категориям
    whiskey_price = whiskey_prices.loc[top_price_shop.shop_id].price
    fruit_price = fruit_prices.loc[top_price_shop.shop_id].price
    choco_price = choco_prices.loc[top_price_shop.shop_id].price
    
    
    sdf = shop_df(top_price_shop)
    whiskey_row = sdf[sdf['category_id'] == whiskey_cat][sdf['price'] == whiskey_price].iloc[0]
    fruit_row = sdf[sdf['category_id'] == fruit_cat][sdf['price'] == fruit_price].iloc[0]
    choco_row = sdf[sdf['category_id'] == choco_cat][sdf['price'] == choco_price].iloc[0]
    # и формируем вывод
    st.subheader(f"Выбран магазин на {top_price_shop.address}")
    cols = st.columns(3)
    
    for index, (row, name) in enumerate(zip([whiskey_row, fruit_row, choco_row], ['Виски', 'Фрукт', "Шоколад"])):
        html_string = f"""
            <h4>{name}: {row.to_dict()["name"]}</h4>
            <img src="{row.img}", width="250"></img><br/>
            <b>Описание: </b> {row.description}
            <h4>{row.price:.2f} рублей</h4>"""
        cols[index].markdown(html_string, unsafe_allow_html=True)


    # и нарисуем маршрут на картах Яндекса
    

    javascript_replace_variables = {
        "CENTER0" : f"{center[0]:.6f}",
        "CENTER1" : f"{center[1]:.6f}",

        "START_POINT0" : f"{start.point[0]:.6f}",
        "START_POINT1" : f"{start.point[1]:.6f}",

        "SHOP_POINTPOINT0" : f"{shop.point.point[0]:.6f}",
        "SHOP_POINTPOINT1" : f"{shop.point.point[1]:.6f}",

        "DEST_POINT0" : f"{dest.point[0]:.6f}",
        "DEST_POINT1" : f"{dest.point[1]:.6f}"
    }


    
    yandex_maps_html = """<html><head>

    <script src="https://ajax.googleapis.com/ajax/libs/jquery/2.1.0/jquery.min.js"></script>
    <script src="https://api-maps.yandex.ru/2.1/?apikey=01c59bdb-2f8c-4140-8d4c-440782c596e0&load=package.standard&lang=ru-RU" type="text/javascript"></script>

    <script>
                ymaps.ready(init);
                function init() {
                    var myMap = new ymaps.Map("map", {
                        center: [CENTER0, CENTER1],
                        zoom: 12
                    }, {
                        searchControlProvider: 'yandex#search'
                    });
                    //Добовляем точки для маршрута
                    ymaps.route([
                        [START_POINT0, START_POINT1],
                        [SHOP_POINTPOINT0, SHOP_POINTPOINT1],
                        [DEST_POINT0, DEST_POINT1]
                    ]).then(function(route) {
                        myMap.geoObjects.add(route);
                        var points = route.getWayPoints(),
                                lastPoint = points.getLength() - 1;
                        points.options.set('preset', 'islands#redStretchyIcon');
                        points.get(0).properties.set('iconContent', 'Откуда');
                        points.get(1).properties.set('iconContent', 'КБ');
                        points.get(lastPoint).properties.set('iconContent', 'Сюда');
                        var moveList = 'Трогаемся,</br>',
                                way,
                                segments;
                        for (var i = 0; i < route.getPaths().getLength(); i++) {
                            way = route.getPaths().get(i);
                            segments = way.getSegments();
                            for (var j = 0; j < segments.length; j++) {
                                var street = segments[j].getStreet();
                                moveList += ('Едем ' + segments[j].getHumanAction() + (street ? ' на ' + street : '') + ', проезжаем ' + segments[j].getLength() + ' м.,');
                                moveList += '</br>'
                            }
                        }
                        moveList += 'Останавливаемся.';
                        // Выводим маршрутный лист.
                        $('#list').append(moveList);
                    }, function(error) {
                        alert('Возникла ошибка: ' + error.message);
                    });
                }
            </script>
            <style>
                body, html {
                    padding: 0;
                    margin: 0;
                    width: 100%;
                    height: 100%;
                    font-family: Arial;
                    font-size: 14px;
                }
                #list {
                    padding: 10px;
                }
                #map {
                    width: 100%; height: 100%;
                }
            </style>
        </head>
        <body>
            <div id="map"></div>
            <div id="list"></div>
        </body>
    </html>
    """

    for k,v in javascript_replace_variables.items():
        yandex_maps_html = yandex_maps_html.replace(k,v)
    # st.write(st.components.html(yandex_maps_html))
    components.html(yandex_maps_html, height=600)
    # st.write(, unsafe_allow_html=True)


    st.subheader("Работа с графами")
    st.write("""
        А теперь давайте представим, что нам нужно проехаться по всем магазинам, купить в каждом по товару, и затем выдвинуться в точку назначения.
        Какой маршрут нужно выбрать, чтобы пройденная дистанция была кратчайшей? 

        При построении маршрута мы будем использовать следующую эвристику:
        - если расстояние от точки А до точки Б по прямой больше, чем от точки А до точки С, то и на карте города А к Б так же ближе
    """)

    

    vertices = [start, *closest_shops, dest]
    edges = {}
    for v_index, v in enumerate(vertices):
        for other_index, other_v in enumerate(vertices):
            try:
                edges[(v_index, other_index)] = v.distance(other_v)
            except:
                try:
                    edges[(v_index, other_index)] = v.distance(other_v.point)
                except:
                    try:
                        edges[(v_index, other_index)] = v.point.distance(other_v)
                    except:
                        edges[(v_index, other_index)] = v.point.distance(other_v.point)
    G = nx.Graph()
    G.add_weighted_edges_from((*k, v) for k,v in edges.items())
    start_index = 0
    end_index = len(vertices)-1
    max_len_paths = [path for path in nx.all_simple_paths(G, start_index, end_index) if len(path) == len(vertices)]
    def path_distance(G, path):
        d = 0
        for s,e in zip(path[:-1], path[1:]):
            d += G.edges[(s,e)]['weight']
        return d
    shortest_path = min(max_len_paths, key=lambda path: path_distance(G, path))
    
    st.write("Ниже изображен построенный маршрут, найденный с помощью библиотеки networkX, на полном графе расстояний между магазинами")

    m = folium.Map(center, zoom_start=12)

    for s,e in zip(shortest_path[:-1], shortest_path[1:]):
        try:
            slat, slon = vertices[s].point
        except:
            slat, slon = vertices[s].point.point
        
        try:
            elat, elon = vertices[e].point
        except:
            elat, elon = vertices[e].point.point
        print(slat, slon, elat, elon)
        folium.PolyLine([(slat, slon), (elat, elon)], color='lightgreen').add_to(m)


    folium.Circle(start.point,radius=50, tooltip=start.description, color="red").add_to(m)
    folium.Circle(dest.point,radius=50, tooltip=dest.description, color="red").add_to(m)
    info_text = []
    info_text.append("Маршрут:")
    
    info_text.append(f"Начало - {start.description}")
    for i, element in enumerate(shortest_path[1:-1], 1):
        info_text.append(f"{i} магазин: {vertices[element].address}")
    info_text.append(f"Конец - {dest.description}")
    st.info("\n\n".join(info_text))
    for index, element in enumerate(shortest_path[1:-1], 1):
        shop = vertices[element]
        description = f"""({index}): {shop.address}"""
        folium.Circle(shop.point.point,radius=30, tooltip=description, color="blue").add_to(m)
    st_m =  st_folium(m, width = 700, height=500)

    st.subheader("Итог")
    st.markdown("""
    Ссылка на критерии: (http://math-info.hse.ru/2021-22/Наука_о_данных/Итоговый_проект): 

        1) Обработка данных с помощью pandas - да 1 балл

        2) Веб-скреппинг - да 1 балл (для получения списка категорий использовались запросы, перехваченные с iphone)

        3) Работа с REST API (XML/JSON). - да 2 балла (api красного и белого не задокументирован)

        4) Визуализация данных - да 1 балл (статистика по магазинам)

        5) Математические возможности Python (содержательное использование numpy/scipy, SymPy и т.д. для решения математических задач). - не

        6) Streamlit - да 1 балл

        7) SQL - не

        8) Регулярные выражения - не

        9) Работа с геоданными - да 1 балл

        10) Машинное обучение - не

        11) Графы - да 1 балл

        12) Доп технологии - да 2 балла (api яндекс карт, ООП)

        13) Объем - да 1 балл (120+ строк)

        14) целостность да 1 балл (все связано)

        15) общее впечатление - на усмотрение проверяющего )
    
    ИТОГО: 12 / 1.5 = 8 баллов
    """)
