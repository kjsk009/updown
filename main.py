try:
    import sys
    import os
    from PyQt5.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox, QRadioButton, QComboBox, QScrollArea, QApplication, QMessageBox
    from PyQt5.QtCore import Qt
    import json
    import random
    import time
    import urllib.request
    import urllib.error
except ImportError as e:
    print(f"필요한 모듈을 찾을 수 없습니다: {e}")
    sys.exit(1)

class DifficultyWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.cleared_songs = self.loadClearedSongs()  # 클리어한 곡들을 불러옴
        self.shown_songs = self.loadShownSongs()  # 각 난이도별로 이미 표시한 곡들을 저장
        self.songs_cache = None  # 곡 데이터 캐시
        self.songs_cache_time = 0  # 캐시 생성 시간
        self.cache_timeout = 300  # 캐시 유효 시간 (초)
        self.songs_url = "https://v-archive.net/db/songs.json"  # 온라인 곡 데이터 URL
        self.last_update_check = 0  # 마지막 업데이트 확인 시간
        self.update_check_interval = 3600  # 업데이트 확인 간격 (1시간)
        self.last_settings = self.loadLastSettings()  # 마지막 설정 불러오기
        self.current_candidates = []  # 현재 추천 후보곡 목록
        self.initUI()
        
    def initUI(self):
        self.setWindowTitle('DJMAX RESPECT V 업다운 순회')
        self.setGeometry(100, 100, 500, 320)  # 높이를 조금 줄임 (버튼 제거로 인해)
        
        # 중앙 위젯 설정
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(5)  # 위젯 간 간격을 더 줄임
        layout.setContentsMargins(10, 10, 10, 10)  # 여백을 더 줄임
        
        # 키 모드 선택
        mode_group = QHBoxLayout()
        mode_group.setSpacing(5)  # 라디오 버튼 간 간격
        self.mode_buttons = {}
        for mode in ['4B', '5B', '6B', '8B']:
            btn = QRadioButton(mode)
            self.mode_buttons[mode] = btn
            mode_group.addWidget(btn)
        
        # 마지막 사용한 모드가 있으면 선택, 없으면 기본값 4B
        last_mode = self.last_settings.get('last_mode', '4B')
        self.mode_buttons[last_mode].setChecked(True)
        
        layout.addLayout(mode_group)
        
        # 난이도 선택
        level_layout = QHBoxLayout()
        level_layout.setSpacing(5)
        level_layout.addWidget(QLabel('난이도:'))
        self.level_combo = QComboBox()
        self.updateLevelCombo()
        
        # 현재 선택된 모드의 마지막 난이도 설정
        current_mode = self.getSelectedMode()
        last_level = self.last_settings.get(current_mode, 8.1)
        last_level_index = self.level_combo.findText(f"{last_level:.1f}")
        if last_level_index >= 0:
            self.level_combo.setCurrentIndex(last_level_index)
            
        level_layout.addWidget(self.level_combo)
        layout.addLayout(level_layout)
        
        # 시작 버튼
        self.start_btn = QPushButton('시작')
        self.start_btn.clicked.connect(self.onStart)
        layout.addWidget(self.start_btn)
        
        # 현재 난이도 표시
        self.level_label = QLabel(f'현재 난이도: {last_level:.1f}')
        self.level_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.level_label)
        
        # 진행도 표시
        self.progress_label = QLabel('진행도: -/-')
        self.progress_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.progress_label)
        
        # 진행도 초기화 버튼 추가
        self.reset_progress_btn = QPushButton('진행도 초기화')
        self.reset_progress_btn.clicked.connect(self.onResetProgress)
        layout.addWidget(self.reset_progress_btn)
        
        # 성공/실패 버튼
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(5)
        self.success_btn = QPushButton('성공')
        self.fail_btn = QPushButton('실패')
        self.success_btn.clicked.connect(self.onSuccess)
        self.fail_btn.clicked.connect(self.onFail)
        btn_layout.addWidget(self.success_btn)
        btn_layout.addWidget(self.fail_btn)
        layout.addLayout(btn_layout)
        
        # 클리어 체크박스와 초기화 버튼을 같은 줄에 배치
        clear_layout = QHBoxLayout()
        self.clear_checkbox = QCheckBox('이 곡 클리어 완료')
        self.clear_checkbox.stateChanged.connect(self.onClearCheck)
        clear_layout.addWidget(self.clear_checkbox)
        
        self.reset_btn = QPushButton('클리어 초기화')
        self.reset_btn.clicked.connect(self.onResetClears)
        clear_layout.addWidget(self.reset_btn)
        layout.addLayout(clear_layout)
        
        # 추천 곡 목록 (스크롤 가능한 영역으로 변경)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        self.song_list = QLabel('추천 곡이 여기에 표시됩니다')
        self.song_list.setWordWrap(True)
        self.song_list.setAlignment(Qt.AlignCenter)
        scroll_content.setLayout(QVBoxLayout())
        scroll_content.layout().setContentsMargins(5, 5, 5, 5)  # 스크롤 영역 내부 여백
        scroll_content.layout().addWidget(self.song_list)
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)
        
        # 버튼 초기 상태
        self.success_btn.setEnabled(False)
        self.fail_btn.setEnabled(False)
        self.clear_checkbox.setEnabled(False)
        
        # 현재 난이도 설정 (선택된 모드의 마지막 사용 난이도)
        self.current_level = last_level
        self.current_song = None
        self.current_pattern = None
        
        # 모든 UI 요소가 생성된 후에 모드 변경 이벤트 연결
        for mode, btn in self.mode_buttons.items():
            btn.toggled.connect(self.onModeChanged)
        
    def updateSongsData(self):
        """온라인에서 곡 데이터를 업데이트합니다. (메시지 없음)"""
        try:
            # 온라인에서 데이터 다운로드
            print("온라인에서 곡 데이터를 다운로드하는 중...")
            with urllib.request.urlopen(self.songs_url, timeout=30) as response:
                online_data = json.loads(response.read().decode('utf-8'))
            
            # 필요한 필드만 필터링
            filtered_data = []
            excluded_fields = ["title", "composer", "dlcCode", "dlc", "rating", "level"]
            
            for song in online_data:
                filtered_song = {}
                for key, value in song.items():
                    if key not in excluded_fields:
                        filtered_song[key] = value
                filtered_data.append(filtered_song)
            
            # 로컬 파일에 저장
            script_dir = os.path.dirname(os.path.abspath(__file__))
            songs_path = os.path.join(script_dir, 'songs.json')
            
            with open(songs_path, 'w', encoding='utf-8') as f:
                json.dump(filtered_data, f, ensure_ascii=False, indent=2)
            
            # 캐시 초기화 (새로운 데이터를 사용하도록)
            self.songs_cache = None
            self.songs_cache_time = 0
            
            print(f"곡 데이터 업데이트 완료: {len(filtered_data)}곡")
            return True
            
        except urllib.error.URLError as e:
            print(f"네트워크 오류: {e}")
            return False
        except json.JSONDecodeError as e:
            print(f"JSON 파싱 오류: {e}")
            return False
        except Exception as e:
            print(f"업데이트 중 오류 발생: {e}")
            return False
            
    def checkForAutoUpdate(self):
        """자동 업데이트 확인 (1시간마다)"""
        current_time = time.time()
        if (current_time - self.last_update_check) > self.update_check_interval:
            self.last_update_check = current_time
            try:
                script_dir = os.path.dirname(os.path.abspath(__file__))
                songs_path = os.path.join(script_dir, 'songs.json')
                
                # 로컬 파일이 없거나 24시간 이상 오래된 경우 자동 업데이트
                if not os.path.exists(songs_path):
                    print("로컬 곡 데이터가 없어 자동 업데이트를 시도합니다.")
                    self.updateSongsData()
                else:
                    file_age = current_time - os.path.getmtime(songs_path)
                    if file_age > 86400:  # 24시간 = 86400초
                        print("곡 데이터가 24시간 이상 오래되어 자동 업데이트를 시도합니다.")
                        self.updateSongsData()
            except Exception as e:
                print(f"자동 업데이트 확인 중 오류: {e}")
                
    def onModeChanged(self):
        """모드가 변경될 때 해당 모드의 마지막 난이도로 콤보박스를 업데이트합니다."""
        if self.sender().isChecked():  # 선택된 라디오 버튼만 처리
            current_mode = self.getSelectedMode()
            last_level = self.last_settings.get(current_mode, 8.1)
            
            # 콤보박스를 해당 모드의 마지막 난이도로 설정
            last_level_index = self.level_combo.findText(f"{last_level:.1f}")
            if last_level_index >= 0:
                self.level_combo.setCurrentIndex(last_level_index)
            
            # 현재 난이도와 라벨 업데이트
            self.current_level = last_level
            self.level_label.setText(f'현재 난이도: {last_level:.1f}')
            
            # 설정 저장
            self.saveLastSettings()
        
    def loadClearedSongs(self):
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            cleared_path = os.path.join(script_dir, 'cleared_songs.json')
            if os.path.exists(cleared_path):
                with open(cleared_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception:
            return {}
            
    def loadShownSongs(self):
        """표시된 곡 진행상황을 로드합니다."""
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            shown_path = os.path.join(script_dir, 'shown_songs.json')
            if os.path.exists(shown_path):
                with open(shown_path, 'r', encoding='utf-8') as f:
                    shown_data = json.load(f)
                    result = {}
                    for level_key, songs in shown_data.items():
                        result[level_key] = set(tuple(song) for song in songs)
                    return result
            return {}
        except Exception as e:
            print(f"표시된 곡 로드 중 오류 발생: {e}")
            return {}
    
    def loadLastSettings(self):
        """마지막 사용 설정을 불러옵니다."""
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            settings_path = os.path.join(script_dir, 'last_settings.json')
            if os.path.exists(settings_path):
                with open(settings_path, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    # 기존 형식 호환성을 위한 마이그레이션
                    if 'level' in settings and 'mode' in settings:
                        # 기존 형식을 새 형식으로 변환
                        old_mode = settings['mode']
                        old_level = settings['level']
                        new_settings = {
                            'last_mode': old_mode,
                            old_mode: old_level,
                            '4B': 8.1, '5B': 8.1, '6B': 8.1, '8B': 8.1
                        }
                        new_settings[old_mode] = old_level
                        return new_settings
                    return settings
            # 기본값: 모든 모드를 8.1로 설정
            return {'last_mode': '4B', '4B': 8.1, '5B': 8.1, '6B': 8.1, '8B': 8.1}
        except Exception as e:
            print(f"마지막 설정 로드 중 오류 발생: {e}")
            return {'last_mode': '4B', '4B': 8.1, '5B': 8.1, '6B': 8.1, '8B': 8.1}
            
    def saveLastSettings(self):
        """현재 설정을 저장합니다."""
        try:
            current_mode = self.getSelectedMode()
            # 현재 모드의 난이도를 업데이트
            self.last_settings['last_mode'] = current_mode
            self.last_settings[current_mode] = self.current_level
            
            script_dir = os.path.dirname(os.path.abspath(__file__))
            settings_path = os.path.join(script_dir, 'last_settings.json')
            with open(settings_path, 'w', encoding='utf-8') as f:
                json.dump(self.last_settings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"설정 저장 중 오류 발생: {e}")
            
    def saveClearedSongs(self):
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            cleared_path = os.path.join(script_dir, 'cleared_songs.json')
            with open(cleared_path, 'w', encoding='utf-8') as f:
                json.dump(self.cleared_songs, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"클리어한 곡 저장 중 오류 발생: {e}")
            
    def saveShownSongs(self):
        """표시된 곡 진행상황을 저장합니다."""
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            shown_path = os.path.join(script_dir, 'shown_songs.json')

            # set 타입은 JSON으로 직렬화할 수 없으므로 리스트로 변환
            shown_data = {}
            for level_key, songs in self.shown_songs.items():
                shown_data[level_key] = [list(song) for song in songs]

            with open(shown_path, 'w', encoding='utf-8') as f:
                json.dump(shown_data, f, ensure_ascii=False, indent=2)

            print(f"진행도 저장 완료: {len(shown_data)}개 난이도")

        except Exception as e:
            print(f"표시된 곡 저장 중 오류 발생: {e}")
            
    def onClearCheck(self, state):
        if self.current_song and self.current_pattern:
            mode = self.getSelectedMode()
            song_key = f"{self.current_song}_{mode}_{self.current_pattern}"
            if state == Qt.Checked:
                self.cleared_songs[song_key] = True
            else:
                if song_key in self.cleared_songs:
                    del self.cleared_songs[song_key]
            self.saveClearedSongs()

    def onResetClears(self):
        reply = QMessageBox.question(self, '클리어 초기화', 
                                   '모든 클리어 기록을 초기화하시겠습니까?',
                                   QMessageBox.Yes | QMessageBox.No, 
                                   QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            self.cleared_songs = {}
            self.saveClearedSongs()
            if self.current_song and self.current_pattern:
                mode = self.getSelectedMode()
                song_key = f"{self.current_song}_{mode}_{self.current_pattern}"
                self.clear_checkbox.setChecked(False)
            QMessageBox.information(self, '초기화 완료', 
                                  '모든 클리어 기록이 초기화되었습니다.')

    def updateLevelCombo(self):
        levels = [
            1.1, 1.2, 1.3, 2.1, 2.2, 2.3, 3.1, 3.2, 3.3,
            4.1, 4.2, 4.3, 5.1, 5.2, 5.3, 6.1, 6.2, 6.3,
            7.1, 7.2, 7.3, 8.1, 8.2, 8.3, 9.1, 9.2, 9.3,
            10.1, 10.2, 10.3, 11.1, 11.2, 11.3, 12.1, 12.2, 12.3,
            13.1, 13.2, 13.3, 14.1, 14.2, 14.3, 15.1, 15.2, 15.3,
            16.1, 16.2
        ]
        self.level_combo.clear()
        for level in levels:
            self.level_combo.addItem(f"{level:.1f}")
            
    def onStart(self):
        # 시작 버튼을 누를 때 곡 데이터 업데이트
        self.start_btn.setEnabled(False)
        self.start_btn.setText('데이터 업데이트 중...')
        QApplication.processEvents()  # UI 업데이트
        
        # 곡 데이터 업데이트 시도
        update_success = self.updateSongsData()
        
        self.start_btn.setEnabled(True)
        self.start_btn.setText('시작')
        
        if not update_success:
            # 업데이트 실패 시 기존 로컬 데이터 사용
            print("온라인 업데이트 실패, 기존 로컬 데이터 사용")
        
        # 현재 난이도 설정
        self.current_level = float(self.level_combo.currentText())
        # 화면 업데이트 (저장된 진행도 유지)
        self.updateDisplay()
        self.success_btn.setEnabled(True)
        self.fail_btn.setEnabled(True)
        self.saveLastSettings()  # 시작할 때 현재 설정 저장
        
    def onResetProgress(self):
        """진행도를 초기화합니다."""
        reply = QMessageBox.question(self, '진행도 초기화', 
                                   '모든 진행도를 초기화하시겠습니까?',
                                   QMessageBox.Yes | QMessageBox.No, 
                                   QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            self.shown_songs = {}  # 모든 난이도의 진행도 초기화
            self.saveShownSongs()  # 초기화된 진행도 저장
            self.updateDisplay()
            QMessageBox.information(self, '초기화 완료', 
                                  '모든 진행도가 초기화되었습니다.')
        
    def getSelectedMode(self):
        return next(mode for mode, btn in self.mode_buttons.items() if btn.isChecked())
        
    def loadSongsData(self):
        """캐시된 곡 데이터를 반환하거나, 필요한 경우 파일에서 새로 로드합니다."""
        current_time = time.time()
        
        # 자동 업데이트 확인
        self.checkForAutoUpdate()
        
        # 캐시가 없거나 만료된 경우
        if self.songs_cache is None or (current_time - self.songs_cache_time) > self.cache_timeout:
            try:
                script_dir = os.path.dirname(os.path.abspath(__file__))
                songs_path = os.path.join(script_dir, 'songs.json')
                
                if not os.path.exists(songs_path):
                    print("로컬 곡 데이터가 없습니다. 시작 버튼을 눌러주세요.")
                    return None
                
                with open(songs_path, 'r', encoding='utf-8') as f:
                    self.songs_cache = json.load(f)
                    self.songs_cache_time = current_time
                    print("곡 데이터를 새로 로드했습니다.")
            except Exception as e:
                print(f"곡 데이터 로드 중 오류 발생: {e}")
                return None
                
        return self.songs_cache

    def updateDisplay(self):
        self.level_label.setText(f'현재 난이도: {self.current_level:.1f}')
        
        songs = self.loadSongsData()
        if songs is None:
            self.song_list.setText('곡 데이터를 로드할 수 없습니다')
            return
            
        try:
            mode = self.getSelectedMode()
            matching_songs = []
            total_songs = 0
            cleared_count = 0
            level_key = f"{mode}_{self.current_level:.1f}"
            
            # 전체 곡 수와 클리어한 곡 수 계산
            for song in songs:
                if mode in song['patterns']:
                    patterns = song['patterns'][mode]
                    for diff_type, info in patterns.items():
                        if isinstance(info, dict) and 'floor' in info:
                            if abs(info['floor'] - self.current_level) < 0.01:
                                total_songs += 1
                                song_key = f"{song['name']}_{mode}_{diff_type}"
                                if song_key in self.cleared_songs:
                                    cleared_count += 1
                                else:
                                    # 클리어하지 않은 곡만 후보에 추가
                                    matching_songs.append((song['name'], f"{diff_type}({info['floor']:.1f})", diff_type))
            
            remaining_songs = total_songs - cleared_count  # 남은 곡 수 계산
            
            # 진행도 표시 (shown_songs에 기록된 개수)
            played_count = 0
            if level_key in self.shown_songs:
                # 실제 played_count 계산
                real_played_count = len(self.shown_songs[level_key])
                
                # 표시용 played_count 계산 (remaining_songs를 초과하지 않도록)
                played_count = min(real_played_count, remaining_songs)
            
            # 진행도 라벨 업데이트
            self.progress_label.setText(f'진행도: {played_count}/{remaining_songs}')
            
            if matching_songs:
                # level_key가 없으면 초기화
                if level_key not in self.shown_songs:
                    self.shown_songs[level_key] = set()
                
                # 아직 보지 않은 곡 필터링
                unplayed_songs = [song for song in matching_songs if (song[0], song[2]) not in self.shown_songs[level_key]]
                
                # 모든 곡을 다 봤을 경우
                if not unplayed_songs:
                    self.song_list.setText('현재 난이도의 모든 곡을 플레이했습니다!')
                    self.clear_checkbox.setEnabled(False)
                    self.current_song = None
                    self.current_pattern = None
                    return
                
                # 랜덤하게 곡 선택
                selected_song = random.choice(unplayed_songs)
                
                # 선택된 곡 정보 저장 (아직 shown_songs에는 추가하지 않음)
                self.current_song = selected_song[0]
                self.current_pattern = selected_song[2]
                
                # 클리어 체크박스 상태 업데이트
                song_key = f"{self.current_song}_{mode}_{self.current_pattern}"
                self.clear_checkbox.setChecked(song_key in self.cleared_songs)
                self.clear_checkbox.setEnabled(True)
                
                # 화면에 선택된 곡 표시
                self.song_list.setText(f"⭐ {selected_song[0]} - {selected_song[1]}")
                
            else:
                if total_songs > 0:  # 곡이 있지만 모두 클리어한 경우
                    self.song_list.setText('현재 난이도의 모든 곡을 클리어했습니다!')
                else:  # 해당 난이도에 곡이 없는 경우
                    self.song_list.setText('선택한 난이도의 곡이 없습니다')
                self.clear_checkbox.setEnabled(False)
                self.current_song = None
                self.current_pattern = None
                
        except Exception as e:
            self.song_list.setText(f'오류 발생: {str(e)}')
            
    def onSuccess(self):
        # 현재 곡이 있으면 항상 진행도에 추가 (중복 체크 없음)
        if self.current_song and self.current_pattern:
            level_key = f"{self.getSelectedMode()}_{self.current_level:.1f}"
            if level_key not in self.shown_songs:
                self.shown_songs[level_key] = set()
                
            # 항상 shown_songs에 추가 (중복 가능)
            self.shown_songs[level_key].add((self.current_song, self.current_pattern))
            self.saveShownSongs()  # 진행도 저장
        
        # 난이도 상승
        levels = [float(self.level_combo.itemText(i)) for i in range(self.level_combo.count())]
        next_level = None
        for level in levels:
            if level > self.current_level:
                next_level = level
                break
        if next_level is not None:
            self.current_level = next_level
        
        # 설정 저장 (난이도 변경 후)
        self.saveLastSettings()
        self.updateDisplay()
        
    def onFail(self):
        # 현재 곡이 있으면 항상 진행도에 추가 (중복 체크 없음)
        if self.current_song and self.current_pattern:
            level_key = f"{self.getSelectedMode()}_{self.current_level:.1f}"
            if level_key not in self.shown_songs:
                self.shown_songs[level_key] = set()
                
            # 항상 shown_songs에 추가 (중복 가능)
            self.shown_songs[level_key].add((self.current_song, self.current_pattern))
            self.saveShownSongs()  # 진행도 저장
        
        # 난이도 하락
        levels = [float(self.level_combo.itemText(i)) for i in range(self.level_combo.count())]
        prev_level = None
        for level in reversed(levels):
            if level < self.current_level:
                prev_level = level
                break
        if prev_level is not None:
            self.current_level = prev_level
        
        # 설정 저장 (난이도 변경 후)
        self.saveLastSettings()
        self.updateDisplay()
    
    def closeEvent(self, event):
        """프로그램 종료 시 현재 설정과 진행상황을 저장합니다."""
        self.saveLastSettings()
        self.saveShownSongs()  # 진행상황 저장
        event.accept()

if __name__ == '__main__':
    try:
        app = QApplication(sys.argv)
        window = DifficultyWindow()
        window.show()
        sys.exit(app.exec_())
    except Exception as e:
        print(f"프로그램 실행 중 오류 발생: {e}")
        sys.exit(1)
