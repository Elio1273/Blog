from django.contrib.auth import logout
from django.shortcuts import render,redirect
from django.views import View


# Create your views here.

#注册视图
from django.http.response import HttpResponseBadRequest
import re
from users.models import User
from django.db import DatabaseError
from django.urls import reverse

class RegisterView(View):
    #注册页面的展示
    def get(self,request):
        return render(request,'register.html')

    def post(self,request):
        #1.接受数据
        mobile=request.POST.get('mobile')
        password = request.POST.get('password')
        password2 = request.POST.get('password2')
        smscode = request.POST.get('sms_code')

        #2.验证数据
        # 2.1 参数是否齐全
        if not all( [mobile,password ,password2, smscode]):
            return HttpResponseBadRequest('缺少必要参数')

        # 2.2 手机号格式是否合法
        if not re.match(r'^1[3-9]\d{9}$', mobile):
            return HttpResponseBadRequest('请输入正确的手机号码')

        # 2.3 密码是否符合格式
        if not re.match(r'^[0-9A-Za-z]{8,20}$', password):
            return HttpResponseBadRequest('请输入8-20位的密码')

        # 2.4 密码两次输入要一致
        if password != password2:
            return HttpResponseBadRequest('两次输入的密码不一致')

        # 2.5 短信验证码是否和redis中的一致
        redis_conn = get_redis_connection('default')
        sms_code_server = redis_conn.get('sms:%s' % mobile)
        if sms_code_server is None:
            return HttpResponseBadRequest('短信验证码已过期')
        if smscode != sms_code_server.decode():
            return HttpResponseBadRequest('短信验证码错误')

        # 3.保存注册信息
        #create_user 可以用系统的方法对密码进行加密
        try:
            user = User.objects.create_user(username=mobile, mobile=mobile, password=password)
        except DatabaseError as e:
            logger.error(e)
            return HttpResponseBadRequest('注册失败')

        from django.contrib.auth import login
        login(request , user)

        # 4.返回响应，跳转到指定页面
        #redirect 是用来重定向的
        #reverse是可以通过namespace：name来获取到视图所对应的路由
        response= redirect(reverse('home:index'))
        #return HttpResponse('注册成功，重定向到首页')

        #设置cookie信息，以方便首页中 用户信息展示的判断和用户信息的展示
        # 设置cookie
        # 登录状态，会话结束后自动过期
        response.set_cookie('is_login', True)
        # 设置用户名有效期一个月
        response.set_cookie('username', user.username, max_age=30 * 24 * 3600)

        return response


#图片验证码视图
from django.http.response import HttpResponseBadRequest
from libs.captcha.captcha import captcha
from django_redis import get_redis_connection
from django.http import HttpResponse

class ImageCodeView(View):
    def get(self,request):

        #1.接收前端传递过来的uuid
        uuid=request.GET.get('uuid')

        #2.判断uuid是否获取到
        if uuid is None:
            return HttpResponseBadRequest('没有传递uuid')

        #3.通过调用captcha来生成图片验证码（图片二进制和图片内容）
        text , image = captcha.generate_captcha()


        #4.将图片内容保存到redis中，uuid作为key，图片内容作为value ，同时还要设置时效
        redis_conn = get_redis_connection('default')
        #key =uuid, seconds =过期秒数 300s , value=text
        redis_conn.setex('img:%s' %uuid , 300 ,text)

        #5.返回图片二进制
        return HttpResponse(image , content_type='image/jpeg')


#手机验证码视图
from django.http.response import JsonResponse
from utils.response_code import RETCODE
import logging
logger=logging.getLogger('django')
from random import randint
from libs.yuntongxun.sms import CCP

class SmsCodeView(View):

    def get(self,request):
        #1.接受参数（查询字符串的形式传递过来）
        mobile=request.GET.get('mobile')
        image_code=request.GET.get('image_code')
        uuid=request.GET.get('uuid')

        #2.参数的验证
        #1）、参数是否齐全
        if not all([mobile ,image_code ,uuid]):
            return JsonResponse({'code' : RETCODE.NECESSARYPARAMERR ,'errmsg' : '缺少必要的参数！'})

        #2）、图片验证码的验证 连接redis，获取redis中的图片验证码，
        redis_conn=get_redis_connection('default')
        redis_image_code=redis_conn.get('img:%s' %uuid)

        #3)判断图片验证码是否存在，
        if redis_image_code is None:
            return JsonResponse({'code' : RETCODE.IMAGECODEERR ,'errmsg' : '图片验证码已过期！' })

        #4)如果未过期，我们就可以删除图片验证码。
        try:
            redis_conn.delete('img:%s' %uuid)
        except Exception as e:
            logger.error(e)

        #5)比对图片验证码,注意大小写。redis数据类型是bytes
        if redis_image_code.decode().lower() !=image_code.lower():
            return JsonResponse({'code' : RETCODE.IMAGECODEERR ,'errmsg' : '图片验证码错误！' })

        #3.生成短信验证码
        sms_code = '%06d' %randint(0,999999)
        #为了后期比对方便，可以将短信验证码记录到日志中
        logger.info(sms_code)


        #4.保存短信验证码到redis中
        redis_conn.setex('sms:%s' %mobile ,300, sms_code)


        #5.发送短信
        #参数一 手机号
        #参数二 【短信验证码 ，有效分钟】
        #参数三 只能使用免费的模板1
        CCP().send_template_sms(mobile , [sms_code,5], 1)


        #6.返回响应
        return JsonResponse({'code': RETCODE.OK, 'errmsg': '短信发送成功！'})



#登录视图
class LoginView(View):
    def get(self,request):


        return render(request,'login.html')

    def post(self,request):
        # 1.接收参数
        mobile = request.POST.get('mobile')
        password = request.POST.get('password')
        remember = request.POST.get('remember')

        # 2.参数的验证
        # 2.1 验证手机号是否符合规则
        if not re.match(r'^1[3-9]\d{9}$', mobile):
            return HttpResponseBadRequest('请输入正确的手机号')

        # 2.2 验证密码是否正确
        if not re.match(r'^[0-9A-Za-z]{8,20}$', password):
            return HttpResponseBadRequest('密码最少8位，最长20位')

        # 3.用户认证登录
        #采用系统自带的认证方式进行认证，如果用户名和密码正确，会返回user；若不正确，会返回none
        #但是默认的认证方法，是用username字段进行判断的，我们需要把认证字段改成手机号
        from django.contrib.auth import authenticate
        # 认证字段已经在User模型中的USERNAME_FIELD = 'mobile'修改
        user = authenticate(mobile=mobile, password=password)
        if user is None:
            return HttpResponseBadRequest('用户名或密码错误')

        # 4.状态保持
        from django.contrib.auth import login
        login(request, user)

        # 响应登录结果
        next = request.GET.get('next')
        if next:
            response = redirect(next)
        else:
            response = redirect(reverse('home:index'))


        # 5.根据用户是否选择 记住登录状态来进行判断
        if remember !='on':#没有选择记住登录状态
            request.session.set_expiry(0)#浏览器关闭之后，就删除登录状态了
            response.set_cookie('is_login', True)
            response.set_cookie('username', user.username, max_age=30 * 24 * 3600)
        else:
            request.session.set_expiry(None)#默认记住两周时间
            response.set_cookie('is_login', True, max_age=14 * 24 * 3600)
            response.set_cookie('username', user.username, max_age=30 * 24 * 3600)

        # 6.为了首页显示 我们需要设置一些cookie信息

        # 7.返回响应
        return response



#退出登录视图
class LogoutView(View):
    def get(self,request):
        # 1.session 数据的清除
        logout(request)

        # 2. 删除部分cooki数据
        response = redirect(reverse('home:index'))

        # 3.跳转到首页
        response.delete_cookie('is_login')

        return response



#忘记密码视图
from django.views import View
class ForgetPasswordView(View):
    def get(self, request):
        return render(request, 'forget_password.html')

    def post(self, request):
        # 1.接受数据
        mobile = request.POST.get('mobile')
        password = request.POST.get('password')
        password2 = request.POST.get('password2')
        smscode = request.POST.get('sms_code')

        # 2.验证数据
        # 2.1 判断参数是否齐全
        if not all([mobile, password, password2, smscode]):
            return HttpResponseBadRequest('缺少必传参数')

        # 2.2 判断手机号是否符合规则
        if not re.match(r'^1[3-9]\d{9}$', mobile):
            return HttpResponseBadRequest('请输入正确的手机号码')

        # 2.3 判断密码是否符合规则
        if not re.match(r'^[0-9A-Za-z]{8,20}$', password):
            return HttpResponseBadRequest('请输入8-20位的密码')

        # 2.4 判断两次密码输入是否一致
        if password != password2:
            return HttpResponseBadRequest('两次输入的密码不一致')

        # 2.5 判断短信验证码是否正确
        redis_conn = get_redis_connection('default')
        sms_code_server = redis_conn.get('sms:%s' % mobile)
        if sms_code_server is None:
            return HttpResponseBadRequest('短信验证码已过期')
        if smscode != sms_code_server.decode():
            return HttpResponseBadRequest('短信验证码错误')

        # 3.根据手机号进行用户信息的查询
        try:
            user = User.objects.get(mobile=mobile)
        except User.DoesNotExist:
            # 如果该手机号不存在，则注册个新用户
            try:
                User.objects.create_user(username=mobile, mobile=mobile, password=password)
            except Exception:
                return HttpResponseBadRequest('修改失败，请稍后再试')
        else:
            # 修改用户密码
            user.set_password(password)
            user.save()#一定要保存用户信息


        # 6.跳转到登录页面
        response = redirect(reverse('users:login'))

        # 7.返回响应
        return response



#用户中心
from django.contrib.auth.mixins import LoginRequiredMixin
#如果用户未登录的话，则会进行默认的跳转（默认跳转链接：accounts/login/next=）
class UserCenterView(LoginRequiredMixin,View):
    def get(self, request):
        # 获取用户信息
        user = request.user

        # 组织模板渲染数据
        context = {
            'username': user.username,
            'mobile': user.mobile,
            'avatar': user.avatar.url if user.avatar else None,
            'user_desc': user.user_desc
        }
        return render(request, 'center.html', context=context)

    def post(self, request):
        # 接收数据
        user = request.user
        avatar = request.FILES.get('avatar')#头像
        username = request.POST.get('username', user.username)
        user_desc = request.POST.get('desc', user.user_desc)

        # 保存信息，修改数据库数据
        try:
            user.username = username
            user.user_desc = user_desc
            if avatar:
                user.avatar = avatar
            user.save()
        except Exception as e:
            logger.error(e)
            return HttpResponseBadRequest('更新失败，请稍后再试')

        # 返回响应，刷新页面
        response = redirect(reverse('users:center'))

        # 更新cookie信息，因为要换右上角的用户名
        response.set_cookie('username', user.username, max_age=30 * 24 * 3600)
        return response



from home.models import ArticleCategory,Article
class WriteBlogView(LoginRequiredMixin,View):

    def get(self,request):
        # 获取博客分类信息
        categories = ArticleCategory.objects.all()

        context = {
            'categories': categories
        }

        return render(request, 'write_blog.html', context=context)

    def post(self, request):
        # 接收数据
        avatar = request.FILES.get('avatar')
        title = request.POST.get('title')
        category_id = request.POST.get('category')
        tags = request.POST.get('tags')
        sumary = request.POST.get('sumary')
        content = request.POST.get('content')
        user = request.user

        # 验证数据是否齐全
        if not all([avatar, title, category_id, sumary, content]):
            return HttpResponseBadRequest('参数不全')

        # 判断文章分类id数据是否正确
        try:
            article_category = ArticleCategory.objects.get(id=category_id)
        except ArticleCategory.DoesNotExist:
            return HttpResponseBadRequest('没有此分类信息')

        # 保存到数据库
        try:
            article = Article.objects.create(
                author=user,
                avatar=avatar,
                category=article_category,
                tags=tags,
                title=title,
                sumary=sumary,
                content=content
            )
        except Exception as e:
            logger.error(e)
            return HttpResponseBadRequest('发布失败，请稍后再试')

        # 返回响应，跳转到文章详情页面
        # 暂时先跳转到首页
        return redirect(reverse('home:index'))





