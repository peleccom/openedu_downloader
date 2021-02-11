import os
import re

import lxml.html as html
import requests
from getpass import getpass

from progressbar import progress

CHUNK_SIZE = 1024 * 1024


class OpenEduException(Exception):
    pass


class OpenEduLoginException(OpenEduException):
    pass


def create_folder(path, folder_name):
    # Функция создает директорию по заданному пути
    if not os.path.exists(path + "/" + re.sub('[^\w_.)( -]', '', folder_name)):
        os.makedirs(path + "/" + re.sub('[^\w_.)( -]', '', folder_name))


def downloader(url, name, file_type='.mp4'):
    # Функция осуществляет загрузку видео-файла по url, в файл name
    name += file_type
    r = requests.get(url, stream=True)
    if not os.path.exists(name):
        total_length = int(r.headers.get('content-length'))
        dl = 0
        filename = name
        if len(name) > 260:
            print("\n{0}\n{1}\nИмена файлов слишком длинны для перемещения в эту целевую папку. Лекции будет присвоено имя формата 'Лекция №'".format(
                *list(map(list, re.findall(r'.*/(.*)/(.*)', name)))[0]) + "\n")
            filename = re.findall(r'(.*Лекция \d*)', name)[0] + file_type
        with open(filename, 'wb') as f:
            for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
                dl += len(chunk)
                if chunk:
                    f.write(chunk)
                progress(dl, total_length)
    else:
        print('Файл ' + name + ' уже существует')


def authorizer_and_pagegetter(username, password, URL='https://sso.openedu.ru/login/', next_page='/oauth2/authorize%3Fstate%3DYpbWrm0u6VoE6nOvTi47PQLaC5CB5ZFJ%26redirect_uri%3Dhttps%3A//openedu.ru/complete/npoedsso/%26response_type%3Dcode%26client_id%3D808f52636759e3616f1a%26auth_entry%3Dlogin'):
    # Функция авторизуется и загружает страницу курса для парсинга. Возвращает страницу курса
    client = requests.session()
    csrf = client.get(URL).cookies['csrftoken']
    login_data = dict(username=username, password=password,
                      csrfmiddlewaretoken=csrf, next=next_page)
    r = client.post(URL, data=login_data, headers=dict(
        Referer=URL),  allow_redirects=False)
    if r.status_code != 302:
        # Нет редиректа. Неверный логин или пароль
        raise OpenEduLoginException('Неверный логин или пароль')
    return client


def page_parser(page):
    # Функция осуществляет парсинг страниц. Возвращает словарь со следующе структурой: ключ - название модуля, значение - список из 2-х элементов
    # первый - название урока, второй - ссылка на страницу урока
    modules = {}
    html_page = html.fromstring(page)
    for x in html_page.find_class('outline-item section'):
        section_titles = x.find_class('section-title')
        if not section_titles:
            continue
        modul_name = section_titles[0].text
        lst = []
        for y in x.find_class('vertical outline-item focusable'):
            lst.append([y.find_class('vertical-title')[0].text_content().strip(),
                        y.find_class('outline-item')[1].attrib['href']])
        modules[modul_name] = lst
    return modules


def content_finder(page):
    # функция ищет все видео с темы + названия видео, а так же ссылки на конспект лекций
    video_url_pattern = r'https://video.*?\.mp4'
    title_pattern = r'data-page-title="(.*?)"'
    summary_pattern = r'href=&#34;(.*)&#34; .*Конспект лекции.*/a'
    if re.findall(video_url_pattern, page) != [] and re.findall(title_pattern, page) != []:
        return list(zip(
            re.findall(video_url_pattern, page)[1::],
            re.findall(title_pattern, page),
            # TODO uncomment
            # re.findall(summary_pattern, page)
        ))
    else:
        return 1


def main():
    username = input('Ваш логин или email: ')
    password = getpass('Ваш пароль: ')
    course_url = input(
        'Ссылка на курс (на вкладку "Курс") в виде URL-а на страницу: ').strip()
    download_path = re.sub(
        r'\\', '/', (input('Ссылка на папку  (по умолчанию, текущая папка): ')))
    if download_path == '':
        download_path = '.'

    course_domain = re.findall(r'(.*)\.ru/.*', course_url)[0] + '.ru'
    client = authorizer_and_pagegetter(username, password)
    page = client.get(course_url).text
    download_path += "/" + \
        re.findall(r'<div class="coursename-title(.*)">(.*)</div>', page)[0][1]
    table = page_parser(page)
    count = 1
    for i in table:
        create_folder(download_path, i)
        total_paths = len(table)
        print('Page {} out of {}:'.format(count, total_paths))
        for j in table[i]:
            content_list = content_finder(client.get(j[1]).text)
            g = 1
            if content_list != 1:
                length = len(content_list)
                for content in content_list:
                    video_url = content[0]
                    video_name = content[1]
                    # TODO uncomment
                    summary_url = course_domain  # + '/' + content[2]
                    chapter_name = re.sub('[^\w_.)( -]', '', i)
                    numbered_video_name = re.sub('[^\w_.)( -]', '', video_name)

                    print('[{}/{}] Downloading... {}'.format(g, length, video_url))
                    downloader(video_url, download_path + "/" + chapter_name +
                               "/" + "Лекция {0} ".format(g) + numbered_video_name)
                    # TODO uncomment
                    # print('[{}/{}] Downloading... {}'.format(g, length, summary_url))
                    # downloader(summary_url, download_path + "/" + chapter_name + "/" + "Конспект {0} ".format(g) + numbered_video_name, file_type = '.pdf')
                    g += 1
        count += 1

    client.close()
    print("Закачка закончена. Если были какие-то замечания или пожелания - напишите, пожалуйста, авторам скрипта.")


if __name__ == '__main__':
    try:
        main()
    except OpenEduLoginException:
        print('\n', 'Неверный логин или пароль')
    except Exception:
        print('\n', 'Проверьте корректность введенных данных и наличие курса. \nТочно ссылка на вкладку "Курс"? \nВсе верно? Тогда, пожалуйста, сообщите авторам скрипта. Вы поможете сделать скрипт еще лучше.')
        raise
