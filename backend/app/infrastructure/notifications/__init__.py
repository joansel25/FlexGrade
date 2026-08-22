"""Adaptador de notificaciones.

Contendrá `smtp_notification_service.py` con SMTPNotificationService, la implementación del
puerto `NotificationService` para avisar al estudiante de una inscripción o una cancelación.

Es el ejemplo canónico del principio abierto/cerrado en este proyecto: añadir un canal nuevo
(SMS, push) significa añadir otra implementación del mismo puerto, sin tocar los casos de uso.
"""
