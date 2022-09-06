from django.db import models
from django.contrib.auth.models import AbstractUser
# Create your models here.

class User(AbstractUser):
    #手机号
    mobile=models.CharField(max_length=11 , unique=True , blank=False)
    #头像信息
    avatar=models.ImageField(upload_to='avatar/ %y%m%d /' , blank=True)
    #简介信息
    user_desc=models.CharField(max_length=500 , blank=True)

    # 认证字段已经在User模型中的USERNAME_FIELD = 'mobile'修改
    USERNAME_FIELD = 'mobile'
    class Meta:
        db_table='tb_users' #修改表名
        verbose_name='用户管理' #admin后台显示
        verbose_name_plural=verbose_name #admin后台显示


    def __str__(self):
        return self.mobile