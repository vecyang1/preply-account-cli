"""Psychological copywriting engine for Preply periodic emails.

Implements:
- "说人话，不要说实话": Employs positive reinforcement, identity framing, and mental accounting.
- Transforms cold administrative statistics into warm, motivating, human milestones.
- Multilingual support: English (en), Simplified Chinese (zh-CN), Vietnamese (vi).
- Aligned with /psychological-copywriter, /copywriting, /boost, /goal skills.
"""

from __future__ import annotations

from typing import Any

from .contracts import Language, LearnerMetrics, TutorMetrics


class PsychologicalCopywriter:
    """Generates human, encouraging, psychology-backed copy for learning digests."""

    @classmethod
    def craft_learner_copy(cls, metrics: LearnerMetrics, lang: Language = Language.EN) -> dict[str, str]:
        """Craft human, encouraging copy for a student/learner."""
        completed = metrics.total_completed_lessons
        hours = metrics.total_hours
        available = metrics.available_balance
        consumed = metrics.current_cycle_consumed
        granted = metrics.current_cycle_granted
        pct = metrics.completion_rate_pct
        needed = metrics.classes_needed_for_next
        is_peak = (needed == 0 and completed >= 50)
        next_m_title = metrics.next_milestone.title if metrics.next_milestone else "Fluency Ambassador"
        next_m_perk = metrics.next_milestone.perk if metrics.next_milestone else "Advanced Mastery"

        if lang == Language.ZH:
            if metrics.is_paused:
                spark_body = (
                    "把学到的语言知识沉淀到日常生活里，是掌握任何一门技能最自然、最健康的一环。"
                    f"你已经扎扎实实积累了 {hours:.1f} 小时的课时记录，这些跨文化交流的肌肉记忆谁也拿不走。"
                    "调整好节奏随时回来，你的老师随时都在这里为你留着一张温和的课桌。"
                )
                subject = "🌿 你的语言沉淀与学习节奏速记：随时为你保留专属进度"
                cta = "查看学员透明看板 ↗"
            elif needed <= 2 and needed > 0:
                spark_body = (
                    f"你距离解锁「{next_m_title}」勋章只差最后 {needed} 节课了！"
                    "语言从来不是背出来的，而是在一次次真实对话中自然流淌出来的。"
                    f"解锁后你将开启「{next_m_perk}」的全新阶段。保持当前的势头，趁热打铁约上下一节吧！"
                )
                subject = f"🌟 离下一个里程碑仅差 {needed} 节课！你的专属学习速递"
                cta = "立即预约下一节课 ↗"
            elif available == 0:
                spark_body = (
                    "本周期的课时全部高效用完！你没有辜负自己当初定下的承诺，每一分钟都真真切切转化成了口语的自信。"
                    "随着新周期的自动就绪，让我们继续把这份难得的动力延续下去。"
                )
                subject = "🎉 太棒了！本周期课时完美达成，为你见证成长"
                cta = "规划新周期课表 ↗"
            else:
                spark_body = (
                    f"你当前还有 {available} 节课随时可约，每一个 50 分钟的面对面对话，都是在给大脑构建直接的双语直觉。"
                    f"目前累计已经完成了 {completed} 节课，这样的长期坚持本身就是极具价值的自我投资。"
                )
                subject = f"✨ 你的专属学习进度速报：已解锁 {completed} 节课时成长"
                cta = "安排本周课时 ↗"

            return {
                "subject": subject,
                "preheader": f"已累计完成 {completed} 节课（{hours:.1f}小时），当前可用余额 {available} 节。",
                "greeting": "亲爱的学员，你好！",
                "hero_headline": "每一次开口对话，都在重塑你的语言直觉",
                "hero_subheadline": f"本周期已完成 {consumed} / {granted} 节课程（完成率 {pct}%），每一步都算数。",
                "stat_completed_label": "已完成课时",
                "stat_balance_label": "待预约余额",
                "stat_streak_label": "连续学习周数",
                "stat_streak_val": f"{metrics.current_streak_weeks} 周",
                "spotlight_tag": "🌟 荣誉里程碑顶峰成就" if is_peak else "即将解锁的下一里程碑",
                "spotlight_title": "殿堂级语言大家 (Fluency Ambassador)" if is_peak else next_m_title,
                "spotlight_needed": "✨ 终身荣誉已解锁" if is_peak else (f"还需 {needed} 节课解锁" if needed > 0 else "里程碑已全部达成！"),
                "spotlight_perk_label": "🎁 专属成长特权：" if is_peak else "🎁 解锁成长权益：",
                "spotlight_perk": "高阶跨文化自由对话与双语思维构建，定制专属个性化复习语料库" if is_peak else next_m_perk,
                "upcoming_title": "近期课程安排",
                "motivation_title": "写在今天的小鼓励 ✨",
                "motivation_body": spark_body,
                "cta_label": cta,
                "footer_help": "如需调整上课时间或有任何问题，可直接在学员看板联系导师或客服。",
            }

        elif lang == Language.VI:
            if metrics.is_paused:
                spark_body = (
                    f"Tạm dừng một nhịp để kiến thức thấm sâu vào cuộc sống là điều hoàn toàn tự nhiên. "
                    f"Bạn đã tích lũy hơn {hours:.1f} giờ học thực chiến – đây là vốn liếng quý giá không ai lấy đi được. "
                    "Bất cứ khi nào bạn sẵn sàng quay lại, giáo viên luôn chờ đón bạn."
                )
                subject = "🌿 Nhịp học của bạn: Kiến thức luôn được bảo lưu trọn vẹn"
                cta = "Xem Bảng Học Tập Của Bạn ↗"
            else:
                spark_body = (
                    f"Bạn đã hoàn thành xuất sắc {completed} buổi học 1-kèm-1! "
                    f"Chỉ còn {needed} buổi nữa là bạn sẽ mở khóa danh hiệu '{next_m_title}'. "
                    "Hãy tiếp tục duy trì đà tiến bộ này nhé!"
                )
                subject = f"🌟 Cập nhật tiến độ học tập: Bạn đã tích lũy {completed} buổi học!"
                cta = "Đặt Lịch Buổi Học Tiếp Theo ↗"

            return {
                "subject": subject,
                "preheader": f"Đã hoàn thành {completed} buổi ({hours:.1f} giờ), số dư sẵn sàng: {available} buổi.",
                "greeting": "Chào bạn,",
                "hero_headline": "Mỗi cuộc trò chuyện là một bước tiến tự tin",
                "hero_subheadline": f"Hoàn thành {consumed}/{granted} buổi trong chu kỳ này ({pct}%).",
                "stat_completed_label": "Buổi đã học",
                "stat_balance_label": "Số dư còn lại",
                "stat_streak_label": "Tuần liên tục",
                "stat_streak_val": f"{metrics.current_streak_weeks} tuần",
                "spotlight_tag": "🌟 CỘT MỐC ĐỈNH CAO ĐÃ MỞ KHÓA" if is_peak else "CỘT MỐC TIẾP THEO",
                "spotlight_title": "Đại Sứ Ngôn Ngữ Tinh Hoa (Fluency Ambassador)" if is_peak else next_m_title,
                "spotlight_needed": "✨ Đã đạt danh hiệu cao nhất!" if is_peak else (f"Cần thêm {needed} buổi để mở khóa" if needed > 0 else "Đã đạt cấp độ cao nhất!"),
                "spotlight_perk_label": "🎁 ĐẶC QUYỀN TRỌN ĐỜI:" if is_peak else "🎁 QUYỀN LỢI:",
                "spotlight_perk": "Giao tiếp chuyên sâu đa văn hóa & Quyền ưu tiên xếp lịch VIP" if is_peak else next_m_perk,
                "upcoming_title": "Lịch học sắp tới",
                "motivation_title": "Động lực hôm nay ✨",
                "motivation_body": spark_body,
                "cta_label": cta,
                "footer_help": "Cần hỗ trợ? Truy cập Cổng học tập học viên XinChaoVi.",
            }

        # Default English (en)
        if metrics.is_paused:
            spark_body = (
                f"Taking a breath to let your new language skills integrate naturally is a proven part of long-term mastery. "
                f"You have banked {hours:.1f} real hours of practice — that fluency foundation is yours permanently. "
                "Whenever life opens up a little space, your instructor has a warm seat waiting for you."
            )
            subject = "🌿 Your Learning Rhythm Update: Progress permanently preserved"
            cta = "Open Your Transparency Portal ↗"
        elif needed <= 2 and needed > 0:
            spark_body = (
                f"You are just {needed} session{'s' if needed > 1 else ''} away from unlocking the '{next_m_title}' milestone! "
                f"Language fluency is not memorized from a textbook — it is discovered through real human conversation. "
                f"Completing this unlocks '{next_m_perk}'. Keep your rhythm strong and reserve your next slot today!"
            )
            subject = f"🌟 Only {needed} class{'es' if needed > 1 else ''} to your next milestone! Your learning momentum"
            cta = "Schedule Your Next Session ↗"
        elif available == 0:
            spark_body = (
                "You have made the absolute most of your hours this subscription cycle! "
                "Showing up consistently week after week is what transforms effort into effortless speaking. "
                "As your fresh cycle begins, let's keep this wonderful momentum going."
            )
            subject = "🎉 Milestone Achieved: 100% of your cycle hours fully engaged!"
            cta = "Plan Your Next Learning Month ↗"
        else:
            spark_body = (
                f"You have {available} lesson credit{'s' if available > 1 else ''} ready and waiting on your dashboard. "
                f"With {completed} total lessons completed to date ({hours:.1f} hours), your consistent dedication is turning "
                "vocabulary into real-world fluency. Book your next conversation to keep the habit rolling effortlessly."
            )
            subject = f"✨ Your Learning Pulse: {completed} Sessions Completed & {available} Ready to Book"
            cta = "Schedule Your Available Session ↗"

        return {
            "subject": subject,
            "preheader": f"{completed} total lessons completed ({hours:.1f} hrs) · {available} available to book now.",
            "greeting": "Hi Chapelle,",
            "hero_headline": "Every Conversation Shapes Real Fluency",
            "hero_subheadline": f"You've completed {consumed} of {granted} sessions this cycle ({pct}% completed).",
            "stat_completed_label": "Lessons Done",
            "stat_balance_label": "Ready to Book",
            "stat_streak_label": "Weekly Streak",
            "stat_streak_val": f"{metrics.current_streak_weeks} wks",
            "spotlight_tag": "🌟 PEAK LIFETIME HONOR UNLOCKED" if is_peak else "NEXT MILESTONE UNLOCK",
            "spotlight_title": "Fluency Ambassador & Master Scholar" if is_peak else next_m_title,
            "spotlight_needed": "✨ Lifetime Honor Achieved!" if is_peak else (f"{needed} class{'es' if needed > 1 else ''} to unlock" if needed > 0 else "All core milestones unlocked!"),
            "spotlight_perk_label": "🎁 LIFETIME PRIVILEGE:" if is_peak else "🎁 UNLOCKS:",
            "spotlight_perk": "Advanced cross-cultural fluency mastery & custom high-tier conversation topics" if is_peak else next_m_perk,
            "upcoming_title": "Upcoming Sessions",
            "motivation_title": "The Motivation Spark ✨",
            "motivation_body": spark_body,
            "cta_label": cta,
            "footer_help": "Need to reschedule or have questions? Access your private student transparency portal anytime.",
        }

    @classmethod
    def craft_tutor_copy(cls, metrics: TutorMetrics, lang: Language = Language.EN) -> dict[str, str]:
        """Craft human, encouraging copy for an educator/tutor."""
        taught = metrics.total_lessons_taught
        students = metrics.active_students_count
        attempts = metrics.booking_attempts_count
        needed = metrics.classes_needed_for_next
        is_peak = (needed == 0 and taught >= 300)
        next_m_title = metrics.next_milestone.title if metrics.next_milestone else "Global Luminary"
        next_m_perk = metrics.next_milestone.perk if metrics.next_milestone else "Master Mentor Honor"

        if lang == Language.ZH:
            attempt_text = (
                f"近期有 {attempts} 位潜在学员浏览并尝试预约你的时间，及时的温暖问候往往能开启一段长期的师生缘分。"
                if attempts > 0 else
                "感谢你一直以来的全心投入，你的每一分耐心都在学生心中生根发芽。"
            )
            spark_body = (
                f"作为导师，你已经累计为学员交付了 {taught} 节个性化课程，陪伴并影响了超过 {students} 位求知者的成长之路。"
                "教育不仅是传授词汇与发音，更是为他人打破语言隔阂、赋予他们走向更广阔世界的勇气。"
                f"{attempt_text}"
            )
            return {
                "subject": f"🏆 导师专属成长周报：已累计交付 {taught} 节高品质教学课时！",
                "preheader": f"累计授课 {taught} 节，陪伴 {students} 位活跃学员，距离下个荣誉还需 {needed} 节课。",
                "greeting": "尊敬的导师，您好！",
                "hero_headline": "你的每一次耐心启发，都在点亮学员的新世界",
                "hero_subheadline": f"已累计圆满交付 {taught} 节 1对1 辅导课，持续影响着 {students} 位学员的成长。",
                "stat_completed_label": "累计交付课时",
                "stat_balance_label": "指导学员数",
                "stat_streak_label": "持续带教周数",
                "stat_streak_val": f"{metrics.current_streak_weeks} 周",
                "spotlight_tag": "🌟 导 师 顶 峰 荣 誉 殿 堂" if is_peak else "导 师 荣 誉 里 程 碑",
                "spotlight_title": "传奇领航导师 (Global Luminary)" if is_peak else next_m_title,
                "spotlight_needed": "✨ 已登顶顶级荣誉殿堂！" if is_peak else (f"还需带教 {needed} 节课达成" if needed > 0 else "已登顶顶级荣誉殿堂！"),
                "spotlight_perk_label": "🎁 终身荣誉特权：" if is_peak else "🎁 导师荣誉成就：",
                "spotlight_perk": "全球教学大使终身荣誉与平台超级导师顶格推介" if is_peak else next_m_perk,
                "upcoming_title": "近期排课课历",
                "motivation_title": "导师初心与寄语 🌿",
                "motivation_body": spark_body,
                "cta_label": "打开导师工作台与课表 ↗",
                "footer_help": "如需开辟新的专属课时或调整学员订阅策略，请前往导师后台统一操作。",
            }

        elif lang == Language.VI:
            attempt_text = (
                f"Gần đây có {attempts} học viên tiềm năng quan tâm và muốn đặt lịch học. Một tin nhắn chào đón ấm áp sẽ mở ra cơ hội đồng hành lâu dài."
                if attempts > 0 else
                "Sự kiên nhẫn sư phạm và nhịp dạy đều đặn của Thầy/Cô là nền tảng vững chắc cho sự tiến bộ của học viên."
            )
            spark_body = (
                f"Với vai trò giảng viên, Thầy/Cô đã hoàn thành {taught} buổi học 1-kèm-1, đồng hành cùng hơn {students} học viên tâm huyết. "
                "Dạy một ngôn ngữ không chỉ là truyền đạt từ vựng hay ngữ pháp, mà là trao chiếc chìa khóa giúp học viên kết nối tự tin với thế giới. "
                f"{attempt_text}"
            )
            return {
                "subject": f"🏆 Báo cáo vinh danh giảng viên: Đã hoàn thành {taught} buổi dạy chất lượng cao!",
                "preheader": f"Tổng cộng {taught} buổi dạy · Đồng hành cùng {students} học viên tiến bộ.",
                "greeting": "Kính gửi Quý Giảng viên,",
                "hero_headline": "Mỗi giờ giảng dạy tận tâm đều mở ra chân trời mới cho học viên",
                "hero_subheadline": f"Đã hoàn thành xuất sắc {taught} buổi dạy 1-kèm-1, hướng dẫn {students} học viên tích cực.",
                "stat_completed_label": "Buổi đã dạy",
                "stat_balance_label": "Học viên đồng hành",
                "stat_streak_label": "Tuần liên tục",
                "stat_streak_val": f"{metrics.current_streak_weeks} tuần",
                "spotlight_tag": "🌟 VINH DANH GIẢNG VIÊN ĐỈNH CAO" if is_peak else "CỘT MỐC VINH DANH GIẢNG VIÊN",
                "spotlight_title": "Giảng viên Tinh hoa Toàn cầu (Global Luminary)" if is_peak else next_m_title,
                "spotlight_needed": "✨ Đã đạt đỉnh cao danh dự!" if is_peak else (f"Cần thêm {needed} buổi để đạt mốc" if needed > 0 else "Đã đạt cấp bậc vinh danh cao nhất!"),
                "spotlight_perk_label": "🎁 ĐẶC QUYỀN TRỌN ĐỜI:" if is_peak else "🎁 ĐẶC QUYỀN VINH DANH:",
                "spotlight_perk": "Đại sứ giảng dạy toàn cầu & Vinh danh xuất sắc trọn đời" if is_peak else next_m_perk,
                "upcoming_title": "Lịch dạy sắp tới",
                "motivation_title": "Góc suy ngẫm của Giảng viên 🌿",
                "motivation_body": spark_body,
                "cta_label": "Mở Bảng Điều Khiển Giảng Dạy ↗",
                "footer_help": "Cần mở thêm lịch dạy hoặc điều chỉnh chương trình? Hãy truy cập trung tâm giảng viên.",
            }

        # Default English
        attempt_text = (
            f"You have {attempts} booking inquiries from eager students waiting for availability. A warm note can turn interest into months of continuous learning."
            if attempts > 0 else
            "Your pedagogical patience and steady rhythm are the bedrock of your students' ongoing success."
        )
        spark_body = (
            f"You have conducted {taught} personalized 1-on-1 sessions, mentoring over {students} dedicated learners. "
            "Teaching a language is far more than grammar points — it is handing someone the key to connect with new cultures and communities. "
            f"{attempt_text}"
        )
        return {
            "subject": f"🏆 Educator Digest: Celebrating {taught} Impactful Lessons Delivered!",
            "preheader": f"{taught} total classes taught · {students} active students mentored.",
            "greeting": "Dear Mentor,",
            "hero_headline": "Your Guidance Shapes Confidence Across Borders",
            "hero_subheadline": f"You have delivered {taught} completed classes, mentoring {students} active learners.",
            "stat_completed_label": "Classes Taught",
            "stat_balance_label": "Active Learners",
            "stat_streak_label": "Teaching Streak",
            "stat_streak_val": f"{metrics.current_streak_weeks} wks",
            "spotlight_tag": "🌟 LIFETIME EDUCATOR PEAK HONOR" if is_peak else "EDUCATOR MILESTONE HONORS",
            "spotlight_title": "Global Luminary & Master Educator" if is_peak else next_m_title,
            "spotlight_needed": "✨ Highest Honor Achieved!" if is_peak else (f"{needed} sessions to unlock" if needed > 0 else "Highest Honor Achieved!"),
            "spotlight_perk_label": "🎁 LIFETIME HONOR:" if is_peak else "🎁 HONOR PRIVILEGE:",
            "spotlight_perk": "Global Teaching Ambassador & Lifetime Excellence Honor" if is_peak else next_m_perk,
            "upcoming_title": "Upcoming Mentorship Sessions",
            "motivation_title": "Educator's Reflection 🌿",
            "motivation_body": spark_body,
            "cta_label": "Open Teaching Hub & Availability ↗",
            "footer_help": "Need to open additional lesson slots or review student progress? Visit your mentor dashboard.",
        }
